# Stage 13 — Deployment Automation and Gas Cost Study

> Stage 12 made the system network-aware. Stage 13 makes it **cost-aware**.
>
> The evidence hash proves the file. The network context tells where the proof
> lives. The gas record tells what it cost to put it there.

## 1. Why Deployment Automation?

Stage 12 introduced multi-network configuration: every network JSON carries an
RPC URL key, a chain ID, a contract address key, and explorer templates. But
the contract address itself was assumed to *already exist* — someone had to
deploy `ProofOfExistence.sol` manually (via `forge create` or a console) and
paste the address into `.env`.

Stage 13 closes that gap. One command deploys the contract to any configured
network and records everything about the deployment:

```bash
python -m proof_client.deploy_contract --network anvil --confirm
python -m proof_client.deploy_contract --network sepolia --confirm
python -m proof_client.deploy_contract --network base-sepolia --confirm
```

## 2. Why a Gas Cost Study?

A blockchain proof is not only a cryptographic object; it is also an economic
transaction. Once the system can deploy to multiple networks, the natural next
question is: **how much does evidence actually cost?**

- What does a single-file registration cost on Sepolia vs Base Sepolia?
- How much does Merkle batching save per file?
- How does the saving scale with batch size?

```bash
python -m proof_client.gas_study --network sepolia --batch-size 10 --confirm
```

## 3. Relationship with Stage 12

| Stage 12 | Stage 13 |
|----------|----------|
| Where does the proof live? | How much does it cost to put it there? |
| network configs, chain-ID validation | deployment automation on top of those configs |
| `create_network_context()` (requires contract address) | `create_network_context_for_deployment()` (does not) |
| contract address from env var only | env var → deployment records → clear error |

## 4. Deployment Workflow

Python-first deployment with the Foundry artifact as input:

```
forge build
  → out/ProofOfExistence.sol/ProofOfExistence.json  (abi + bytecode)
  → Python reads the artifact
  → Web3.py builds, signs, broadcasts the constructor transaction
  → DeploymentRecord saved to SQLite
  → optional: .env contract address updated (--update-env)
```

Step by step (`proof_client/deploy_contract.py`):

1. Load the network config and validate RPC + chain ID
   (`create_network_context_for_deployment` — no contract address needed).
2. Refuse non-testnet networks unless `--allow-mainnet` is passed.
3. Load `PRIVATE_KEY`, derive the deployer address, check the balance.
4. Load the Foundry artifact (`--artifact` > `FOUNDRY_ARTIFACT_PATH` > default).
5. Build the constructor transaction, estimate gas (+20% headroom).
6. `--dry-run` stops here — config, wallet, artifact and estimate validated,
   nothing broadcast.
7. Sign, broadcast, wait for the receipt; abort on revert.
8. Compute `deployment_fee = gasUsed × effectiveGasPrice`.
9. Save the `DeploymentRecord` and print all deployment facts including the
   explorer URL.

## 5. Foundry Artifact Loading

The artifact must contain `abi` and `bytecode.object`. Errors are explicit:

- missing file → *"Run `forge build` in the contracts/ directory first"*
- missing `abi` / `bytecode.object` → named validation error

Resolution priority: `--artifact` flag → `FOUNDRY_ARTIFACT_PATH` env var →
`contracts/out/ProofOfExistence.sol/ProofOfExistence.json`.

## 6. Deployment Record Schema

`proof_client/deployment_record.py` — persisted in the `deployment_records`
SQLite table by `proof_client/deployment_repository.py`:

| Field | Meaning |
|-------|---------|
| `contract_name` | e.g. `ProofOfExistence` |
| `network_key`, `network_display_name`, `chain_id` | where it was deployed |
| `contract_address` | the created address |
| `deployer_address` | derived from `PRIVATE_KEY` (the key itself is never stored) |
| `transaction_hash`, `block_number`, `block_timestamp` | on-chain location |
| `gas_used`, `effective_gas_price_wei` | receipt data |
| `deployment_fee_wei`, `deployment_fee_eth` | what the deployment cost |
| `explorer_url`, `artifact_path`, `created_at_utc` | provenance |

## 7. Contract Address Resolution

After Stage 13 a network's contract address can come from two places. The
resolution order (`network_context.resolve_contract_address`):

1. Explicitly supplied address (highest priority, where applicable)
2. `.env` — `<NETWORK>_CONTRACT_ADDRESS`
3. Latest matching row in `deployment_records`
4. `ValueError` naming both the env var and the deploy command

This keeps pre-Stage-13 setups working unchanged while letting a fresh
deployment be used immediately without editing `.env`.

A network now has four status flags (surfaced by `GET /networks`):

- `configured` — a JSON config exists
- `connected` — the RPC answers with the right chain ID (checked at use time)
- `deployed` — a deployment record exists
- `ready` — a contract address is resolvable (env or deployment history)

## 8. Gas Cost Model

`proof_client/gas_cost.py`:

```
total_fee_wei     = gas_used × effective_gas_price_wei
cost_per_file_wei = total_fee_wei // max(file_count, 1)
savings           = 1 − (merkle_cost_per_file / single_file_cost_per_file)
```

`contract_client.register_hash` now returns `effective_gas_price_wei` from the
receipt, and every register result carries the full cost breakdown.
`EvidenceRecord` gained `effective_gas_price_wei`, `total_fee_wei`,
`total_fee_eth`, `native_token_symbol`; `BatchEvidence` additionally gained
`cost_per_file_wei` / `cost_per_file_eth`. SQLite migrations add the columns
idempotently, so old databases keep working.

## 9. Gas Study Methodology

`proof_client/gas_study.py` runs standardised experiments on one network:

| Workflow | Files | Transactions |
|----------|-------|--------------|
| `single_file` | N | N |
| `merkle_batch` | N | 1 |
| `ipfs` (optional) | N | N |
| `encrypted_ipfs` (optional) | N | N |

Sample files are generated deterministically
(`proof_client/generate_gas_samples.py`): content is a fixed function of
(index, salt). Because the contract rejects re-registration of an existing
hash, each study salts its samples with its study ID by default; passing an
explicit `--salt` makes runs byte-for-byte reproducible. Within one study,
each workflow gets its own sub-salt so no hash is registered twice.

Outputs, under `reports/gas_studies/<study_id>/`:

```
gas_study.json         full study record
gas_study.csv          flat per-transaction table
transactions.json      raw per-transaction records
gas_study.md           Markdown report
gas_study_report.pdf   PDF report
README.md              study overview
samples/               the deterministic input files
```

## 10. Single-File vs Merkle Batch Comparison

The report (`proof_client/gas_report.py`) aggregates per-workflow totals and
computes:

- `cost_per_file` and `gas_per_file` for each workflow
- `merkle_savings_percentage` — how much cheaper per file the batch is

The Merkle batch pays for one fixed-cost transaction regardless of how many
file hashes the root covers, so the per-file saving grows with the batch size
(the batch transaction is only marginally more expensive than a single
registration, but is divided across N files).

## 11. API Endpoints

```
GET  /deployments                     list deployment records (?network=)
GET  /deployments/latest?network=k    latest deployment for a network
POST /deployments/deploy              deploy (requires confirm=true)

GET  /gas/studies                     list studies
GET  /gas/studies/{study_id}          study + per-workflow summaries + savings
GET  /gas/studies/{study_id}/report   download (format = md|json|csv|pdf)
POST /gas/studies/run                 run a study (requires confirm=true)
```

Both POST endpoints reject requests without `confirm=true`:

```json
{
  "status": "error",
  "message": "Deployment requires confirm=true because it broadcasts an on-chain transaction."
}
```

`dry_run=true` is exempt from the confirm requirement because it never
broadcasts.

## 12. Dashboard Pages

- `/dashboard/deploy` — network selector, dry-run / update-env toggles, and a
  mandatory confirm checkbox
- `/dashboard/deployments` — deployment history table with explorer links
- `/dashboard/gas-study` — study runner with workflow toggles and confirm
  checkbox
- `/dashboard/gas-studies` — study list
- `/dashboard/gas-studies/{study_id}` — per-workflow cost table, Merkle
  savings banner, JSON/CSV/MD/PDF downloads

Every transaction-broadcasting form displays:

> ⚠️ This action broadcasts on-chain transactions and may spend testnet or
> real native tokens.

## 13. Security Boundaries

1. **Mainnet disabled by default** — non-testnet configs are refused unless
   `--allow-mainnet` / `allow_mainnet=true` is explicit.
2. **Confirm required everywhere** — CLI `--confirm`, API `confirm=true`,
   dashboard confirm checkbox; all broadcast paths are gated.
3. **Dry run never broadcasts** — validates config, wallet, artifact, and gas
   estimate only.
4. **`PRIVATE_KEY` is never output** — not in records, reports, logs, API
   responses, or error messages (the missing-key error names the variable,
   never its value).
5. **Errors do not leak `.env` contents** — messages reference env var *names*
   only.

## 14. Test Strategy

Six suites, all mocked at the `register_hash` / Web3 seam (no live RPC):

| Suite | Focus | Tests |
|-------|-------|-------|
| `proof_client.test_stage13_deployment` | record, repository, resolution, context, artifact, guards, mocked deploy | 86 |
| `proof_client.test_stage13_gas_cost` | cost maths, schema fields, migrations, register integration | 65 |
| `proof_client.test_stage13_gas_study` | samples, study run, workflows, dry-run, reports, CLI | 89 |
| `api.test_stage13_deployment_api` | endpoints, confirm guard, network status, key safety | 46 |
| `api.test_stage13_gas_api` | endpoints, formats, confirm guard, path safety | 41 |
| `api.test_stage13_dashboard` | pages, forms, confirm checkboxes, rendering | 46 |

Stage 13 total: **373**. All previous suites (690 checks) still pass.

## 15. Limitations

- Gas prices fluctuate; a study is a snapshot, not a forecast.
- Testnet gas prices do not reflect mainnet economics; L2 costs also include a
  data-availability component that testnets underestimate.
- IPFS pinning/storage costs are off-chain and not measured.
- The deployment CLI uses legacy `gasPrice` transactions (matching the
  registration path); EIP-1559 fee fields are a possible refinement.
- Mainnet deployment is intentionally out of scope for this stage.
