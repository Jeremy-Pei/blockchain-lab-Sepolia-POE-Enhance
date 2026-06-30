# Stage 12 — Multi-Network Evidence Support

## Overview

Stage 12 upgrades the Proof-of-Existence (PoE) Python client from a single-network (Sepolia) system to a **network-aware evidence framework**. The CLI, REST API, and web dashboard can all select which EVM-compatible network to use at registration and verification time. The initial release supports three networks out of the box:

| Key            | Display Name      | Chain ID | Explorer                      |
|----------------|-------------------|----------|-------------------------------|
| `anvil`        | Anvil Local       | 31337    | (none — local node)           |
| `sepolia`      | Ethereum Sepolia  | 11155111 | https://sepolia.etherscan.io  |
| `base_sepolia` | Base Sepolia      | 84532    | https://sepolia.basescan.org  |

---

## Architecture

### 1. Network JSON Configs (`python-client/networks/`)

Each supported network is described by a single JSON file:

```
python-client/networks/
  anvil.json
  sepolia.json
  base_sepolia.json
```

JSON schema (all fields):

```json
{
  "network_key":                  "sepolia",
  "display_name":                 "Ethereum Sepolia",
  "chain_id":                     11155111,
  "rpc_url_env_key":              "SEPOLIA_RPC_URL",
  "contract_address_env_key":     "SEPOLIA_CONTRACT_ADDRESS",
  "explorer_base_url":            "https://sepolia.etherscan.io",
  "explorer_tx_url_template":     "https://sepolia.etherscan.io/tx/{tx_hash}",
  "explorer_address_url_template":"https://sepolia.etherscan.io/address/{address}",
  "native_token_symbol":          "ETH",
  "is_testnet":                   true,
  "enabled":                      true
}
```

`rpc_url_env_key` and `contract_address_env_key` point to environment variable names — the actual values are **never hardcoded** in the config files.

---

### 2. `network_config.py` — Config Layer

```python
from proof_client.network_config import (
    normalize_network_key,   # "base-sepolia" → "base_sepolia"
    load_network_config,     # loads JSON, returns NetworkConfig dataclass
    list_network_configs,    # all enabled configs sorted by network_key
    get_default_network_key, # reads DEFAULT_NETWORK env var, falls back to "sepolia"
    get_default_network_config,
)
```

`NetworkConfig` is a `@dataclass` with computed properties:

```python
cfg = load_network_config("sepolia")
cfg.rpc_url          # os.getenv("SEPOLIA_RPC_URL", "")
cfg.contract_address # os.getenv("SEPOLIA_CONTRACT_ADDRESS", "")
cfg.tx_url("0xabc…") # "https://sepolia.etherscan.io/tx/0xabc…"
cfg.address_url("0x…") # "https://sepolia.etherscan.io/address/0x…"
```

**Key normalisation** happens at load time: `"base-sepolia"` → `"base_sepolia"`, case-insensitive, strips whitespace. Unknown keys raise `ValueError` listing available networks.

---

### 3. `network_context.py` — Web3 Context (optional)

When a live connection is needed, `create_network_context(network_key)` builds a validated `NetworkContext`:

1. Reads `rpc_url` and `contract_address` from env vars
2. Connects `Web3` via HTTP provider
3. Validates `eth.chain_id` matches the JSON `chain_id` — prevents mis-wired RPC+contract

---

### 4. Network Resolution Priority

Throughout the system, network resolution uses this priority order:

```
1. Explicit --network argument (CLI) or network= form field (API)
2. network_key stored in the local evidence record  ← verify flow only
3. DEFAULT_NETWORK environment variable
4. Falls back to "sepolia"
```

---

## Environment Variables

```bash
# Default network when --network is not specified
DEFAULT_NETWORK=sepolia

# Anvil (local Foundry test node)
ANVIL_RPC_URL=http://127.0.0.1:8545
ANVIL_CONTRACT_ADDRESS=0x...

# Ethereum Sepolia
SEPOLIA_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY
SEPOLIA_CONTRACT_ADDRESS=0x...

# Base Sepolia
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/YOUR_KEY
BASE_SEPOLIA_CONTRACT_ADDRESS=0x...
```

Copy `.env.example` to `.env` and fill in your values.

---

## CLI Usage

All four CLI tools now accept `--network`:

```bash
# Register a file on Anvil (local dev)
python -m proof_client.register_file paper.pdf --network anvil

# Register on Base Sepolia
python -m proof_client.register_file paper.pdf --network base-sepolia

# Verify — uses evidence record's stored network if not specified
python -m proof_client.verify_file paper.pdf

# Verify on a specific network
python -m proof_client.verify_file paper.pdf --network base_sepolia

# Batch Merkle register on Anvil
python -m proof_client.batch_merkle_register works/ --network anvil

# Verify a Merkle proof
python -m proof_client.verify_merkle_proof --file doc.txt --proof proof.json
# (network key read from proof.json's network_key field automatically)
```

---

## REST API

### New Endpoints

| Method | Path                       | Description                        |
|--------|----------------------------|------------------------------------|
| GET    | `/networks`                | List all enabled networks          |
| GET    | `/networks/current`        | Current default network info       |
| GET    | `/networks/{network_key}`  | Single network info (404 if unknown) |

**GET /networks** response example:

```json
{
  "status": "ok",
  "count": 3,
  "networks": [
    {
      "network_key": "anvil",
      "display_name": "Anvil Local",
      "chain_id": 31337,
      "is_testnet": true,
      "explorer_base_url": "",
      "enabled": true
    },
    { "network_key": "base_sepolia", "chain_id": 84532, ... },
    { "network_key": "sepolia", "chain_id": 11155111, ... }
  ]
}
```

### Updated Endpoints

All existing endpoints accept an optional `network` form field:

```bash
# Register on Base Sepolia
curl -X POST /register/file \
  -F "file=@paper.pdf" \
  -F "network=base_sepolia"

# Verify on Anvil
curl -X POST /verify/file \
  -F "file=@paper.pdf" \
  -F "network=anvil"

# Batch register on Sepolia
curl -X POST /batches/merkle/register \
  -F "folder_path=/path/to/works" \
  -F "network=sepolia"
```

Omitting `network` falls back to `DEFAULT_NETWORK` env var.

---

## Dashboard

### Network Badge

Every page shows a network badge in the top navigation:

```
📌 POE System  [Ethereum Sepolia]
```

### Home Page Info

The home page displays current network details:

- Network name and key
- Chain ID
- Contract address (truncated)

### Network Selector

Register, Verify, and Batch pages include a dropdown:

```html
<select name="network">
  <option value="">Default (Ethereum Sepolia)</option>
  <option value="anvil">Anvil Local (31337)</option>
  <option value="base_sepolia">Base Sepolia (84532)</option>
  <option value="sepolia" selected>Ethereum Sepolia (11155111)</option>
</select>
```

---

## Data Schema Changes

### EvidenceRecord (evidence_schema.py)

Two new optional fields (backward-compatible, default `""`):

```python
@dataclass
class EvidenceRecord:
    ...
    network_key: str = ""         # e.g. "sepolia", "base_sepolia"
    explorer_base_url: str = ""   # e.g. "https://sepolia.etherscan.io"
```

### BatchEvidence (merkle_evidence.py)

Same two fields added to `BatchEvidence`.

### SQLite Migration

The repository auto-migrates existing databases:

```sql
ALTER TABLE evidence ADD COLUMN network_key TEXT DEFAULT '';
ALTER TABLE evidence ADD COLUMN explorer_base_url TEXT DEFAULT '';
ALTER TABLE batch_evidence_records ADD COLUMN network_key TEXT DEFAULT '';
ALTER TABLE batch_evidence_records ADD COLUMN explorer_base_url TEXT DEFAULT '';
```

The `ensure_column()` pattern means migration is idempotent — safe to run against any pre-Stage-12 database.

### Proof JSON

Merkle proof JSON files now include network metadata:

```json
{
  "batch_id": "batch-20240101",
  "network_key": "base_sepolia",
  "network": "Base Sepolia",
  "chain_id": 84532,
  "contract_address": "0x...",
  ...
}
```

---

## Backward Compatibility

- All new fields default to `""` — old JSON files and SQLite rows load cleanly
- Old CLI invocations without `--network` work unchanged (use `DEFAULT_NETWORK` or default to sepolia)
- API clients that don't send `network=` get the default network
- `EvidenceRecord.from_dict()` filters unknown keys, so extra or missing fields are harmless

---

## Test Coverage

| Test File                              | Count | Description                              |
|----------------------------------------|-------|------------------------------------------|
| `proof_client/test_stage12_networks.py`| 90    | Config loading, normalisation, migration, CLI flags, integration |
| `api/test_stage12_networks_api.py`     | 55    | REST API network endpoints + dashboard   |

Run:

```bash
cd python-client
PYTHONPATH=. .venv/bin/python -m proof_client.test_stage12_networks
PYTHONPATH=. .venv/bin/python -m api.test_stage12_networks_api
```

---

## Adding a New Network

1. Create `python-client/networks/my_network.json`
2. Add the env vars to `.env`
3. Deploy your contract to the target chain
4. Run `GET /networks` to confirm it appears

No code changes needed — the system discovers JSON files at runtime.
