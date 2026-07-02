# How Much Does Blockchain Evidence Cost? Stage 13 of a Proof-of-Existence System

*Stage 13 of an ongoing blockchain development series*

---

Stage 12 made the system network-aware: every evidence record knows which chain it lives on, which RPC it used, which explorer to link to. But it quietly left two questions open. First, a practical one — the contract address in every network config was assumed to *already exist*, deployed by hand and pasted into `.env`. Second, an economic one — nobody could say what any of this actually costs.

Stage 13 answers both. A blockchain proof is not only a cryptographic object; it is also an economic transaction.

---

## Part 1: Deployment as a First-Class Operation

Until now, deploying `ProofOfExistence.sol` meant running `forge create` somewhere, copying the address, and editing `.env`. That's fine once. It stops being fine when you have three networks and plan to add more.

The new deployment CLI treats Foundry and Python as a pipeline: Foundry compiles, Python deploys.

```bash
forge build   # in contracts/ — produces the artifact JSON

python -m proof_client.deploy_contract --network base-sepolia --confirm
```

The script loads the artifact's ABI and bytecode, validates the RPC and chain ID, checks the deployer balance, estimates gas with 20% headroom, broadcasts, and waits for the receipt. Then it prints everything you'd want to write down — and writes it down for you:

```
network_key:                 base_sepolia
chain_id:                    84532
contract_address:            0x...
deployment_transaction_hash: 0x...
gas_used:                    481634
deployment_fee_eth:          0.000481634001444902 ETH
explorer_url:                https://sepolia.basescan.org/tx/0x...
```

### The Chicken-and-Egg Context

One design wrinkle worth calling out: Stage 12's `create_network_context()` refuses to run without a contract address — which is correct for registration, and impossible for deployment, since deployment is what *creates* the address. The fix is a second constructor, `create_network_context_for_deployment()`, that performs the same RPC and chain-ID validation but skips the address requirement. Same safety checks, minus the one precondition that cannot logically hold yet.

### Where Does the Address Live Afterwards?

Deployments are recorded in a new SQLite table, and contract address resolution now has a priority chain:

1. `.env` (`<NETWORK>_CONTRACT_ADDRESS`) — explicit user config always wins
2. The latest row in `deployment_records` for that network
3. A clear error naming both the env var and the deploy command

So a fresh deployment is usable immediately — `register_file --network base-sepolia` finds the address from deployment history — while anyone who prefers pinning addresses in `.env` keeps full control. The CLI only touches `.env` if you explicitly pass `--update-env`, and it rewrites exactly one line.

---

## Part 2: The Gas Cost Study

With deployment automated, running controlled cost experiments becomes one command:

```bash
python -m proof_client.gas_study --network base-sepolia --batch-size 10 --confirm
```

The study registers N deterministic sample files two ways:

- **single_file** — N files, N `register()` transactions
- **merkle_batch** — the same N files, one `register(merkle_root)` transaction

and writes `gas_study.json`, `gas_study.csv`, a Markdown report, and a PDF into `reports/gas_studies/<study_id>/`. IPFS and encrypted-IPFS workflows are optional flags, kept out of the default run because network uploads add noise to a gas measurement.

### A Detail That Bit Me: Deterministic Samples vs. a Deduplicating Contract

The samples must be deterministic — random content would make experiments unreproducible. But `ProofOfExistence.register()` reverts on an already-registered hash, so *fully* deterministic content means the second study on the same network fails on its first transaction.

The compromise: sample content is a pure function of (index, salt), and the salt defaults to the study ID. Every study is internally deterministic and never collides with a previous one; passing an explicit `--salt` gives byte-for-byte reproducibility when you want to re-register on a fresh network. Within a study, each workflow gets its own sub-salt so the single-file and Merkle experiments never fight over the same hash.

### What the Numbers Say

The economics are exactly what the Merkle tree design promised back in Stage 9, but now with receipts. One batch transaction costs only marginally more gas than one single registration — yet it covers every file under the root:

```
Single-file cost per file: 0.000072 ETH  (10 transactions for 10 files)
Merkle batch cost per file: 0.0000075 ETH (1 transaction for 10 files)
Merkle batching saves 89.6% per file at this batch size.
```

The saving asymptotically approaches `1 − 1/N`: the batch pays one fixed transaction fee regardless of how many hashes the root commits to. The report computes this as

```
savings = 1 − (merkle_cost_per_file / single_file_cost_per_file)
```

and the trade-off is stated plainly in the Limitations section: batching amortises the fee, but you must keep the per-file Merkle proofs to stay verifiable.

---

## The Safety Rails

Stage 13 is the first stage where a wrong keystroke could spend real money, so the guardrails are strict and tested:

- **Mainnet is disabled by default.** Any config with `is_testnet: false` is refused unless `--allow-mainnet` is passed explicitly.
- **Everything that broadcasts requires confirmation.** `--confirm` on the CLI, `confirm=true` in the API, a checkbox in the dashboard. `--dry-run` is exempt because it validates everything and broadcasts nothing.
- **The private key never leaves the process.** It is not stored in deployment records, not printed, not returned by any endpoint — and the missing-key error names the variable, never its value. There's a test that greps every API response for key material.

---

## Where the System Stands

Thirteen stages in, the pipeline is: hash → register (single, IPFS, encrypted, or Merkle batch) → evidence records → packages → REST API → dashboard → any configured network → with deployment and cost measurement built in. Six new test suites add 373 checks; the full regression across all stages is now over 1,000.

Stage 12 answered *where does the proof live*. Stage 13 answers *what it costs to put it there*. The next obvious step is running the study against real L2 mainnets — where the question "is blockchain evidence affordable?" finally gets a production-grade answer.

The evidence hash proves the file.
The network context tells where the proof lives.
The gas record tells what it cost to put it there.
