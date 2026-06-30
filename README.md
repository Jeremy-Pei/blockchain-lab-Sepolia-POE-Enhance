# Blockchain Lab — Proof of Existence (Sepolia Enhanced)

> 🎓 **Learning project** — A blockchain proof-of-existence prototype for learning
> Solidity + Python + Web3 development.
>
> ⚠️ This is not a production copyright registration product; it is intended for
> technical learning and as a teaching reference.

## Overview

This project implements a **Proof of Existence** system on the Ethereum Sepolia
testnet:

1. Compute the SHA-256 hash of a file
2. Submit the hash to a smart contract
3. Use the blockchain's immutability to prove the file existed at a specific point in time

### Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Smart contract | Solidity 0.8.24 / Foundry | ProofOfExistence contract |
| Client | Python 3.12+ / web3.py | File registration, verification, evidence management |
| Concepts | C++ | Blockchain fundamentals and data structures |
| Testnet | Ethereum Sepolia | On-chain deployment and interaction |

## Project Structure

```
blockchain-lab-Sepolia-POE-Enhance/
│
├── contracts/                  # Solidity smart contracts (Foundry)
│   ├── src/ProofOfExistence.sol
│   ├── test/
│   ├── foundry.toml
│   └── .env.example
│
├── python-client/              # Python client toolkit
│   ├── proof_client/           # Core package
│   │   ├── config.py           #   Unified configuration management
│   │   ├── hash_file.py        #   SHA-256 hash computation
│   │   ├── wallet.py           #   Web3 connection & wallet management
│   │   ├── contract_client.py  #   Contract call wrappers
│   │   ├── evidence_schema.py  #   Evidence data structure (dataclass)
│   │   ├── evidence_store.py   #   Evidence JSON persistence
│   │   ├── evidence_repository.py  # Evidence SQLite persistence
│   │   ├── register_file.py    #   Register a file on-chain
│   │   ├── verify_file.py      #   Verify on-chain registration status
│   │   ├── batch_register.py   #   Batch registration
│   │   ├── generate_report.py  #   Markdown proof report generator
│   │   ├── query_evidence.py   #   Query evidence records
│   │   ├── report_template.py  #   Stage 6: shared certificate content
│   │   ├── pdf_report.py       #   Stage 6: PDF certificate generator
│   │   ├── manifest.py         #   Stage 6: SHA-256 manifest + integrity check
│   │   ├── verification_guide.py   # Stage 6: third-party verification guide
│   │   ├── package_exporter.py #   Stage 6: assemble evidence package + ZIP
│   │   ├── export_package.py   #   Stage 6: CLI to export packages
│   │   ├── verify_package.py   #   Stage 6: CLI to verify package integrity
│   │   ├── ipfs_client.py      #   Stage 7: IPFS clients (mock + Pinata) + helpers
│   │   ├── ipfs_upload.py      #   Stage 7: CLI to upload a file to IPFS
│   │   ├── ipfs_download.py    #   Stage 7: CLI to download a file by CID
│   │   ├── verify_ipfs.py      #   Stage 7: CLI to verify IPFS content vs hash
│   │   ├── crypto_utils.py     #   Stage 8: AES-256-GCM + PBKDF2 primitives
│   │   ├── encrypt_file.py     #   Stage 8: CLI to encrypt a file locally
│   │   ├── decrypt_file.py     #   Stage 8: CLI to decrypt a file
│   │   ├── encrypted_ipfs.py   #   Stage 8: encrypt-then-upload to IPFS
│   │   ├── verify_encrypted_ipfs.py  # Stage 8: download, decrypt, verify
│   │   ├── merkle_tree.py      #   Stage 9: Merkle tree construction + proof
│   │   ├── merkle_evidence.py  #   Stage 9: batch evidence data structures
│   │   ├── merkle_report.py    #   Stage 9: batch Markdown + PDF certificate
│   │   ├── batch_merkle_register.py  # Stage 9: batch registration CLI
│   │   ├── verify_merkle_proof.py    # Stage 9: per-file Merkle proof verify CLI
│   │   ├── test_all.py         #   Full module test suite
│   │   ├── test_stage6.py      #   Stage 6 test suite
│   │   ├── test_stage7.py      #   Stage 7 test suite (IPFS)
│   │   ├── test_stage8.py      #   Stage 8 test suite (encrypted IPFS)
│   │   └── test_stage9.py      #   Stage 9 test suite (Merkle batch)
│   ├── api/                    # Stage 10: FastAPI evidence service
│   │   ├── main.py            #   App factory + routers + error envelope
│   │   ├── services.py        #   Adapter layer over proof_client
│   │   ├── schemas.py         #   Pydantic request/response models
│   │   ├── routes_*.py        #   Health/Files/Register/Verify/Evidence/Packages/Batches
│   │   └── test_stage10_api.py #  Stage 10 test suite (FastAPI)
│   ├── abi/ProofOfExistence.json
│   ├── works/                  #   Files to register
│   ├── uploads/                #   Stage 10: API file uploads
│   ├── evidence/               #   Generated evidence JSON files
│   │   └── batches/            #   Stage 9: batch Merkle evidence dirs
│   ├── reports/                #   Generated proof reports
│   │   └── batches/            #   Stage 9: batch Markdown + PDF certificates
│   ├── packages/               #   Generated evidence packages (ZIP)
│   │   └── batches/            #   Stage 9: batch evidence package ZIPs
│   ├── .env.example
│   └── requirements.txt
│
├── cpp-core/                   # C++ blockchain concept learning
│
├── docs/                       # Design documents
│   ├── proof_of_existence_design.md
│   ├── evidence_package.md
│   └── ...
│
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.12+
- [Foundry](https://getfoundry.sh/) (for contract compilation and deployment)
- Sepolia testnet ETH (available from the [Alchemy faucet](https://www.alchemy.com/faucets/ethereum-sepolia))
- Alchemy / Infura RPC API Key

### 1. Clone the repository

```bash
git clone https://github.com/Jeremy-Pei/blockchain-lab-Sepolia-POE-Enhance.git
cd blockchain-lab-Sepolia-POE-Enhance
```

### 2. Configure environment variables

```bash
# Python client
cd python-client
cp .env.example .env
# Edit .env and fill in your RPC_URL, PRIVATE_KEY, and CONTRACT_ADDRESS
nano .env

# Create a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Usage

```bash
cd python-client
export PYTHONPATH=.

# Compute a file hash
python -m proof_client.hash_file works/sample_work.txt

# Register a file on-chain
python -m proof_client.register_file works/sample_work.txt

# Verify a file
python -m proof_client.verify_file works/sample_work.txt

# Batch-register all files in works/
python -m proof_client.batch_register

# Generate a proof report
python -m proof_client.generate_report <file_hash>
python -m proof_client.generate_report --all

# Query evidence records
python -m proof_client.query_evidence --all
python -m proof_client.query_evidence --hash <file_hash>
python -m proof_client.query_evidence --owner <address>
python -m proof_client.query_evidence --stats
```

### 4. Run tests

```bash
cd python-client
export PYTHONPATH=.

# Local tests only (no on-chain calls, 49 test cases)
python -m proof_client.test_all

# Stage 6: PDF, ZIP package, manifest, verification guide (90 test cases)
python -m proof_client.test_stage6

# Stage 7: IPFS upload/download, CID, verify_ipfs, package metadata (79 test cases)
python -m proof_client.test_stage7

# Stage 8: AES-256-GCM encryption, encrypted IPFS, verify_encrypted_ipfs (75 test cases)
python -m proof_client.test_stage8

# Stage 9: Merkle batch registration, proofs, package, verify CLI (84 test cases)
python -m proof_client.test_stage9

# Stage 10: FastAPI evidence service endpoints (90 test cases)
python -m api.test_stage10_api

# Stage 11: Web evidence dashboard (78 test cases)
python -m api.test_stage11_dashboard

# Stage 12: Multi-network support — core (90 test cases)
python -m proof_client.test_stage12_networks

# Stage 12: Multi-network support — API (55 test cases)
python -m api.test_stage12_networks_api

# Include on-chain tests (requires Sepolia ETH, consumes gas)
python -m proof_client.test_all --chain
```

| Suite | Tests |
|-------|-------|
| Core (`test_all`) | 49 |
| Stage 6 (`test_stage6`) | 90 |
| Stage 7 (`test_stage7`) | 79 |
| Stage 8 (`test_stage8`) | 75 |
| Stage 9 (`test_stage9`) | 84 |
| Stage 10 (`api.test_stage10_api`) | 90 |
| Stage 11 (`api.test_stage11_dashboard`) | 78 |
| Stage 12 core (`proof_client.test_stage12_networks`) | 90 |
| Stage 12 API (`api.test_stage12_networks_api`) | 55 |

## Evidence Package (Stage 6)

Stage 6 turns a raw on-chain registration into a **self-contained, independently
verifiable evidence package** — a single ZIP that a third party can check without
trusting (or even running) this software.

```bash
cd python-client
export PYTHONPATH=.

# Export a verifiable evidence package (ZIP) for one registration
python -m proof_client.export_package --hash <file_hash>
python -m proof_client.export_package --id   <row_id>
python -m proof_client.export_package --all

# Verify a package's integrity (works on a .zip or an extracted folder)
python -m proof_client.verify_package packages/evidence_package_<date>_<short>.zip
```

Each package contains the original file, a machine-readable evidence JSON, Markdown +
PDF certificates, a step-by-step third-party verification guide, and a `manifest.json`
of SHA-256 checksums that makes any post-generation tampering detectable:

```
evidence_package_<date>_<short>/
├── original/        # copy of the registered work file
├── evidence/        # machine-readable on-chain evidence record (JSON)
├── reports/         # human-readable certificate (Markdown + PDF)
├── verification/    # third-party verification guide + copy-paste commands
├── manifest.json    # SHA-256 checksum of every file in the package
└── README.md        # package overview + quick verification steps
```

📄 Full design and verification model: [docs/stage6_evidence_package_system.md](docs/stage6_evidence_package_system.md)

## IPFS Integration (Stage 7)

> 🏷️ Release: [**v0.7.0 — IPFS Integration for Off-Chain Content-Addressed Storage**](https://github.com/Jeremy-Pei/blockchain-lab-Sepolia-POE-Enhance/releases/tag/v0.7.0)

Stage 7 adds an **off-chain, content-addressed storage layer**. The file (or an
encrypted copy) is uploaded to IPFS, and the resulting `ipfs://<CID>` becomes the
on-chain `uri` — so a third party can re-obtain the original bytes, not just the
hash. **The smart contract is unchanged**; its `uri` field was always meant for an
off-chain pointer.

```bash
cd python-client
export PYTHONPATH=.

# Upload a file to IPFS (prints CID, ipfs:// URI, gateway URL, SHA-256)
python -m proof_client.ipfs_upload works/sample_work.txt

# Register on-chain AND pin to IPFS in one step (uri becomes ipfs://<CID>)
python -m proof_client.register_file works/sample_work.txt --upload-ipfs

# Download a file from IPFS by CID
python -m proof_client.ipfs_download <CID> -o downloads/sample_work.txt

# Verify IPFS content against the registered hash
python -m proof_client.verify_ipfs --cid <CID> --expected-hash 0x<hash>
python -m proof_client.verify_ipfs --hash 0x<file_hash>
```

A provider is selected by `IPFS_PROVIDER` (default `mock`, a local network-free
content store ideal for tests; `pinata` uses the Pinata pinning service and needs
`PINATA_JWT`). When a record has a CID, evidence packages gain an `ipfs/` folder
(`ipfs_metadata.json` + `ipfs_gateway_links.txt`), the certificate gains an
**Off-Chain Storage (IPFS)** section, and the verification guide gains
**Step 4 — Verify the IPFS Content**.

> ⚠️ **Privacy:** Do not upload private or sensitive files to public IPFS without
> encryption. For sensitive works, upload an *encrypted copy* rather than the raw
> original. The SHA-256 hash — not the CID — remains the primary evidence hash.

📄 Full design, workflow, and privacy notes: [docs/stage7_ipfs_integration.md](docs/stage7_ipfs_integration.md)

## Encrypted IPFS (Stage 8)

Stage 8 makes the Stage 7 privacy warning actionable. A sensitive file can be
**encrypted locally before** being uploaded to IPFS, so a public gateway only ever
stores ciphertext. The smart contract still registers the **original** file's
SHA-256 hash, while the `uri` field points to the encrypted IPFS CID.

```bash
cd python-client
export PYTHONPATH=.

# Encrypt / decrypt a file locally (password is prompted, never taken from argv)
python -m proof_client.encrypt_file works/my_paper.pdf --output encrypted/my_paper.pdf.enc
python -m proof_client.decrypt_file encrypted/my_paper.pdf.enc \
    --metadata encrypted/my_paper.pdf.enc.metadata.json --output decrypted/my_paper.pdf

# Register on-chain AND upload an ENCRYPTED copy in one step
# (registers the ORIGINAL hash; uri becomes the ciphertext's ipfs://<CID>)
python -m proof_client.register_file works/my_paper.pdf --upload-ipfs --encrypt-before-ipfs

# Verify: download ciphertext, decrypt, recompute the original hash, check on-chain
python -m proof_client.verify_encrypted_ipfs --hash 0x<original_file_hash>
```

Encryption is **AES-256-GCM** with a **PBKDF2-HMAC-SHA256** (600k iterations)
password-derived key, a random 16-byte salt and 12-byte nonce per file. The
ciphertext is authenticated, so a wrong password or any tampering fails on
decrypt. Encrypted records gain an `encrypted/` folder in their evidence package,
an **Encrypted Off-Chain Storage** section in the certificate, and
**Step 5 — Verify Encrypted IPFS Content** in the verification guide; by default
an encrypted package **excludes** the plaintext original.

> 🔐 **The password or encryption key is never stored** in the evidence record,
> the database, the certificate, or the package. If the password is lost, the
> encrypted file cannot be recovered by this system. This is an educational
> prototype and has not been professionally audited.

📄 Full design, threat model, and verification: [docs/stage8_encrypted_ipfs.md](docs/stage8_encrypted_ipfs.md)

## Merkle Batch Registration (Stage 9)

Stage 9 makes registration **scalable and gas-efficient**. Instead of one
blockchain transaction per file, many file hashes are combined into a single
**Merkle tree**, and only the **Merkle root** is registered on-chain. Each file
receives an independent **Merkle proof** so any third party can verify that a
specific file was part of the registered batch.

```
many files
→ many SHA-256 hashes
→ Merkle tree
→ Merkle root
→ one blockchain transaction
→ one proof per file
```

```bash
cd python-client
export PYTHONPATH=.

# Register a batch of files (Merkle root goes on-chain; one proof per file)
python -m proof_client.batch_merkle_register works/ \
    --title "My Evidence Batch" \
    --author "Author Name" \
    --description "Batch proof-of-existence for multiple works."

# Recurse into sub-directories
python -m proof_client.batch_merkle_register works/ --recursive

# Dry-run: build tree and evidence without a blockchain transaction
python -m proof_client.batch_merkle_register works/ --dry-run

# Verify that one file belongs to a registered batch (local only)
python -m proof_client.verify_merkle_proof \
    --file works/paper.pdf \
    --proof evidence/batches/<batch_id>/proofs/paper.pdf.proof.json

# Verify with on-chain confirmation
python -m proof_client.verify_merkle_proof \
    --file works/paper.pdf \
    --proof evidence/batches/<batch_id>/proofs/paper.pdf.proof.json \
    --chain
```

**Merkle tree rules** (fully documented in each `batch_evidence.json` so any
verifier can reproduce them independently):

| Parameter | Rule |
|-----------|------|
| Leaf hash | SHA-256 of file bytes |
| Leaf ordering | Normalised relative path, ascending lexicographic |
| Internal node | SHA-256(left\_bytes \|\| right\_bytes) |
| Odd-level padding | Duplicate the last node |
| Hash encoding | 0x-prefixed lowercase hex |

The batch package mirrors the single-file package structure:

```
merkle_batch_package_<date>_<short>/
├── original/          # copies of registered files
├── batch/             # batch_evidence.json, merkle_tree.json, leaves.json
├── proofs/            # one <file>.proof.json per file
├── reports/           # batch_certificate.md + batch_certificate.pdf
├── verification/      # batch_verification_guide.md + commands
├── manifest.json      # SHA-256 checksums for every file in the package
└── README.md
```

> **What this proves:** A Merkle proof verifies that a file hash was included in
> a registered batch root. It does not prove legal authorship, copyright
> ownership, or originality.

📄 Full design: [docs/stage9_merkle_batch_registration.md](docs/stage9_merkle_batch_registration.md)

## Web Evidence Dashboard (Stage 11)

Stage 11 adds a **local browser-based dashboard** on top of the Stage 10
FastAPI service.  The dashboard provides pages for file hashing, registration,
verification, Merkle proof verification, evidence browsing, batch browsing, and
package downloads — all without leaving the browser.

```bash
cd python-client
PYTHONPATH=. .venv/bin/uvicorn api.main:app --reload
```

Open the dashboard:

```
http://127.0.0.1:8000/
```

Open API docs:

```
http://127.0.0.1:8000/docs
```

Run Stage 11 tests:

```bash
PYTHONPATH=. .venv/bin/python -m api.test_stage11_dashboard
# Stage 11 Dashboard Tests: 78/78 passed
```

> ⚠️ **Local development only.** The dashboard does not implement
> authentication. Do **not** expose it directly to the public internet.

📄 Full design: [docs/stage11_web_dashboard.md](docs/stage11_web_dashboard.md)

## Multi-Network Evidence Support (Stage 12)

Stage 12 upgrades the system from Sepolia-only to a **network-aware evidence framework**. The CLI, API, and dashboard can all select any EVM-compatible network at registration and verification time.

Supported networks out of the box:

| Key            | Display Name      | Chain ID |
|----------------|-------------------|----------|
| `anvil`        | Anvil Local       | 31337    |
| `sepolia`      | Ethereum Sepolia  | 11155111 |
| `base_sepolia` | Base Sepolia      | 84532    |

### Environment Setup

```bash
# .env
DEFAULT_NETWORK=sepolia
SEPOLIA_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY
SEPOLIA_CONTRACT_ADDRESS=0x...
ANVIL_RPC_URL=http://127.0.0.1:8545
ANVIL_CONTRACT_ADDRESS=0x...
BASE_SEPOLIA_RPC_URL=https://base-sepolia.g.alchemy.com/v2/YOUR_KEY
BASE_SEPOLIA_CONTRACT_ADDRESS=0x...
```

### CLI Usage

```bash
# Register on Anvil (local dev)
python -m proof_client.register_file paper.pdf --network anvil

# Register on Base Sepolia
python -m proof_client.register_file paper.pdf --network base-sepolia

# Verify — uses stored network_key from evidence record
python -m proof_client.verify_file paper.pdf

# Batch register on Anvil
python -m proof_client.batch_merkle_register works/ --network anvil
```

### API Network Endpoints

```
GET /networks              → list all enabled networks
GET /networks/current      → current default network
GET /networks/{key}        → single network info (404 if unknown)
```

All existing endpoints accept an optional `network` form field.

### Run Stage 12 Tests

```bash
PYTHONPATH=. .venv/bin/python -m proof_client.test_stage12_networks
# Stage 12 Results: 90/90 passed, 0 failed

PYTHONPATH=. .venv/bin/python -m api.test_stage12_networks_api
# Stage 12 API Results: 55/55 passed, 0 failed
```

### Adding a New Network

1. Create `python-client/networks/my_chain.json`
2. Set `MY_CHAIN_RPC_URL` and `MY_CHAIN_CONTRACT_ADDRESS` in `.env`
3. The system discovers the file at startup — no code changes needed

📄 Full design: [docs/stage12_multi_network_support.md](docs/stage12_multi_network_support.md)

## FastAPI Evidence Service (Stage 10)

Stage 10 exposes the Proof-of-Existence toolkit as a local **FastAPI** service.
The existing CLI workflows are wrapped into HTTP endpoints for file hashing,
registration, verification, evidence query, package export, and Merkle batch
operations — so other programs (and a future Web Dashboard) can drive the
system over REST. The proof model, smart contract, and all previous stages are
unchanged.

```bash
cd python-client
PYTHONPATH=. .venv/bin/uvicorn api.main:app --reload
# Interactive Swagger docs: http://127.0.0.1:8000/docs
```

```bash
# Liveness
curl http://127.0.0.1:8000/health

# Upload a file and get its SHA-256
curl -F "file=@works/sample_work.txt" http://127.0.0.1:8000/files/hash

# Register a file on-chain (multipart form)
curl -F "file=@works/sample_work.txt" -F "title=My Paper" \
     http://127.0.0.1:8000/register/file
```

Endpoint groups: `/health`, `/files`, `/register`, `/verify`, `/evidence`,
`/packages`, `/batches` (20 routes total). Every response carries a `status`
field (`"ok"` / `"error"`).

> ⚠️ **Local development only.** This service can sign on-chain transactions
> using the `.env` private key, read local files, and accept encryption
> passwords. Do **not** expose it to the public internet without authentication,
> rate limiting, input validation, and secure key management.

📄 Full design: [docs/stage10_fastapi_service.md](docs/stage10_fastapi_service.md)

## Smart Contract

[ProofOfExistence.sol](contracts/src/ProofOfExistence.sol) exposes two core methods:

| Method | Type | Description |
|--------|------|-------------|
| `register(bytes32 fileHash, string uri)` | Write | Register a file hash on-chain |
| `verify(bytes32 fileHash)` | Read | Query registration info for a file hash |

### Deploy with Foundry

```bash
cd contracts
cp .env.example .env
# Edit .env

source .env
forge script --broadcast --rpc-url $SEPOLIA_RPC_URL \
  --private-key $SEPOLIA_PRIVATE_KEY \
  script/Deploy.s.sol
```

## Security

> **⚠️ Important:** The `.env` files contain sensitive information and are excluded
> from version control via `.gitignore`.

- **Never commit** a real private key (`PRIVATE_KEY`) to Git
- **Never commit** an RPC URL containing an API Key
- Use `.env.example` as a template and create `.env` locally
- Use a dedicated test wallet isolated from your main wallet

## Use Cases

- 🎓 Blockchain technology learning
- 📖 Solidity + Python engineering reference
- 🔐 Proof-of-Existence prototype
- 👨‍🏫 Teaching and demonstration
- 📝 Technical blog companion code

## License

MIT License — for educational use only.
