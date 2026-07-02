# How Much Does Blockchain Evidence Cost? Stage 13 of a Proof-of-Existence System

*Stage 13 of an ongoing blockchain development series*

---

Stage 12 made this system network-aware: every evidence record knows which chain it lives on, which RPC produced it, which explorer to link to. But it quietly left two questions open.

The first was practical. Every network config assumed its contract address *already existed* — someone had to run `forge create` by hand, copy the address, and paste it into `.env`. Fine for one network. Tedious for three. Unworkable for ten.

The second was economic, and it's the more interesting one. This project has spent twelve stages building cryptographic machinery — SHA-256 hashes, Merkle trees, AES-GCM encryption — and never once asked what any of it costs to use. A blockchain proof is not only a cryptographic object; it is also an economic transaction. Somebody pays gas for every root that gets registered.

Stage 13 answers both questions. Deployment becomes one command. Cost becomes a number you can measure, compare, and put in a report.

---

## Part 1: Deployment as a Pipeline, Not a Ritual

There were two candidate designs for deployment automation. Option A: have Python shell out to `forge script` and parse its output. Option B: let Foundry do what it's best at (compiling) and let Python do what the rest of this codebase already does (talking to chains through Web3).

I chose B — *Foundry compiles, Python deploys* — and the deciding factor was integration, not elegance. The Python side already has network configs, chain-ID validation, SQLite persistence, and a test harness that mocks the Web3 seam. A `forge script` subprocess would sit outside all of that: cross-platform shell quirks, stdout parsing, and no natural place to record what happened.

The pipeline reads the artifact that `forge build` already produces:

```
forge build
  → out/ProofOfExistence.sol/ProofOfExistence.json   (abi + bytecode)
  → Python loads the artifact
  → Web3.py builds, signs, broadcasts the constructor tx
  → DeploymentRecord saved to SQLite
  → optional --update-env rewrites one line of .env
```

```bash
python -m proof_client.deploy_contract --network base-sepolia --confirm
```

The output is every fact you'd otherwise scribble into a notes file: network key, chain ID, contract address, deployer, transaction hash, block number, gas used, effective gas price, the fee in ETH, and the explorer URL.

---

## The Chicken-and-Egg Context

One design wrinkle deserves its own section. Stage 12's `create_network_context()` validates three things before letting you touch a chain: the RPC URL exists, the node's reported chain ID matches the config, and a contract address is resolvable. That third check is exactly right for registration — and logically impossible for deployment, because deployment is the step that *creates* the address.

The fix is a second constructor:

```python
def create_network_context_for_deployment(network_key=None) -> NetworkContext:
    # same RPC + chain-ID validation, no contract address required
```

Same safety net, minus the one precondition that cannot hold yet. Both constructors share the connection-and-validation helper, so the chain-ID mismatch error — the one that catches a Sepolia RPC pointed at Base — fires identically in both paths.

---

## Where Does the Address Live Afterwards?

After a deployment there are two possible sources of truth for a network's contract address: the env var, and the `deployment_records` table. I didn't want the new machinery to silently override anyone's explicit configuration, so resolution is a strict priority chain:

```python
def resolve_contract_address(network_key: str) -> str:
    # 1. <NETWORK>_CONTRACT_ADDRESS env var        (explicit config wins)
    # 2. latest deployment_records row             (deploy → use, no .env edit)
    # 3. ValueError naming the env var AND the deploy command
```

The practical effect: `register_file --network base-sepolia` works immediately after a deployment with no `.env` edit, but an address pinned in `.env` always wins. And the CLI only touches `.env` when you pass `--update-env` explicitly — it rewrites exactly the one matching line and preserves everything else byte-for-byte. Automatically mutating a user's secrets file as a side effect felt like the kind of convenience that turns into a bug report.

This also gave `/networks` a proper status model. A network is `configured` (JSON exists), `deployed` (a deployment record exists), and `ready` (an address is resolvable from either source) — three flags that used to be one ambiguous "is it set up?"

---

## Part 2: The Gas Study

With deployment automated, controlled cost experiments become one command:

```bash
python -m proof_client.gas_study --network base-sepolia --batch-size 10 --confirm
```

The study registers N sample files two ways and measures both:

| Workflow | Files | Transactions |
|----------|-------|--------------|
| `single_file` | N | N |
| `merkle_batch` | N | 1 |

IPFS and encrypted-IPFS workflows exist behind `--include-ipfs` / `--include-encrypted-ipfs` flags but stay out of the default run — network uploads add latency and failure modes that have nothing to do with gas, and a measurement tool should measure one thing.

Each study writes a self-contained directory under `reports/gas_studies/<study_id>/`: the raw per-transaction records (JSON), a flat table (CSV), a Markdown report, a PDF, and the sample files themselves.

---

## A Detail That Bit Me: Deterministic Samples vs. a Deduplicating Contract

Gas experiments should be reproducible, so sample files must have deterministic content — random bytes would make every run measure different hashes. I wrote the generator that way, felt good about it, and then remembered line one of the contract:

```solidity
function register(bytes32 fileHash, string calldata uri) external {
    require(records[fileHash].timestamp == 0, "Already registered");
```

Fully deterministic content means the *second* study on the same network reverts on its first transaction, because those hashes are already on-chain from the first study.

The compromise: sample content is a pure function of `(index, salt)`, and the salt defaults to the study ID. Every study is internally deterministic and never collides with a previous one. Passing an explicit `--salt` restores byte-for-byte reproducibility for a fresh network. And within one study, each workflow gets its own sub-salt (`{salt}:single_file`, `{salt}:merkle_batch`, …) so the single-file experiment and the Merkle experiment never fight over the same hash either.

It's a small design point, but it's the kind that only surfaces when a cryptographic system meets an economic one: the contract's deduplication is a *feature* for evidence and an *obstacle* for benchmarking.

---

## What the Numbers Say

The receipts confirm what the Merkle tree design promised back in Stage 9. One batch transaction costs only marginally more gas than one single registration — but it covers every file under the root:

```
Single-file cost per file:  0.000072  ETH   (10 transactions for 10 files)
Merkle batch cost per file: 0.0000075 ETH   (1 transaction for 10 files)
Merkle batching saves 89.6% per file at this batch size.
```

The report computes the headline number as:

```
savings = 1 − (merkle_cost_per_file / single_file_cost_per_file)
```

and the saving asymptotically approaches `1 − 1/N`, because the batch pays one near-fixed fee regardless of how many hashes the root commits to. The Limitations section states the trade-off plainly: batching amortises the fee, but you must retain the per-file Merkle proofs to stay verifiable — the cost doesn't disappear, it moves from gas to storage discipline.

One implementation note: costs are computed from the receipt's `gasUsed × effectiveGasPrice`, not from the gas price the client *asked* for. `contract_client.register_hash` now returns `effective_gas_price_wei`, and the cost fields flow into `EvidenceRecord` and `BatchEvidence` through the same `ensure_column()` idempotent migrations every stage since 7 has used. Old databases and old evidence JSON load unchanged.

---

## The Safety Rails

Stage 13 is the first stage where a wrong keystroke could spend real money, so the guardrails are strict, and each one is tested:

- **Mainnet is disabled by default.** Any config with `is_testnet: false` is refused unless `--allow-mainnet` is passed. There is no mainnet config in the repo; the guard exists for the day there is.
- **Everything that broadcasts requires confirmation.** `--confirm` on the CLI, `confirm=true` in the API (a 400 with an explanatory message otherwise), a checkbox in the dashboard. `--dry-run` is exempt because it validates config, wallet, artifact, and gas estimate — and broadcasts nothing. The test suites assert both halves: dry runs never call `send_raw_transaction`, and unconfirmed requests never reach the deployer.
- **The private key never leaves the process.** Not stored in deployment records, not printed, not returned by any endpoint. The missing-key error names the variable, never its value, and one test greps every API response for key material.

---

## Test Coverage

373 new tests across six files:

- `proof_client/test_stage13_deployment.py` (86): record schema, repository, address resolution priority, deployment context, artifact loading errors, mainnet guard, `.env` rewriting, full mocked deploy flow
- `proof_client/test_stage13_gas_cost.py` (65): cost maths, zero-division and legacy-receipt edge cases, schema fields, SQLite migrations, register integration
- `proof_client/test_stage13_gas_study.py` (89): sample determinism, salt collision avoidance, workflow selection, dry-run, report aggregation, savings computation, CLI gates
- `api/test_stage13_deployment_api.py` (46), `api/test_stage13_gas_api.py` (41), `api/test_stage13_dashboard.py` (46): endpoints, confirm guards, report downloads, page rendering, private-key safety

All mocked at the `register_hash` / Web3 seam — no live RPC needed. The full regression across Stages 1–12 (690 checks) still passes.

---

## What's Next

The obvious next step is pointing the study at real L2 mainnets — Base, Optimism, Arbitrum — where "is blockchain evidence affordable?" finally gets a production-grade answer, and where L1 data-availability fees add a cost component that testnets underestimate. The deployment CLI is one config file away from supporting each of them; the mainnet guard is there precisely so that step is deliberate.

Thirteen stages in, the through-line is intact:

The evidence hash proves the file.
The network context tells where the proof lives.
The gas record tells what it cost to put it there.

---

*Code: github.com/Jeremy-Pei/blockchain-lab-Sepolia-POE-Enhance | Tag: v0.13.0*
