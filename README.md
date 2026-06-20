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
│   │   └── test_all.py         #   Full module test suite
│   ├── abi/ProofOfExistence.json
│   ├── works/                  #   Files to register
│   ├── evidence/               #   Generated evidence JSON files
│   ├── reports/                #   Generated proof reports
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

# Include on-chain tests (requires Sepolia ETH, consumes gas)
python -m proof_client.test_all --chain
```

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
