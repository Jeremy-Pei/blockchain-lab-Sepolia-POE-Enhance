"""
config.py — Unified configuration management

Loads environment variables from .env and provides project path constants.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# ── Project paths ─────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

ABI_DIR = PROJECT_ROOT / "abi"
WORKS_DIR = PROJECT_ROOT / "works"
EVIDENCE_DIR = PROJECT_ROOT / "evidence"
REPORTS_DIR = PROJECT_ROOT / "reports"
PACKAGES_DIR = PROJECT_ROOT / "packages"
DB_PATH = PROJECT_ROOT / "evidence.db"

# Stage 7: local content store used by the mock IPFS client
MOCK_IPFS_DIR = PROJECT_ROOT / "mock_ipfs_storage"

# Ensure required directories exist
for d in (WORKS_DIR, EVIDENCE_DIR, REPORTS_DIR, PACKAGES_DIR, MOCK_IPFS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Blockchain configuration ──────────────────────────────────────
RPC_URL = os.getenv("RPC_URL", "")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
CHAIN_ID = int(os.getenv("CHAIN_ID", "11155111"))
EXPLORER_TX_URL = os.getenv("EXPLORER_TX_URL", "https://sepolia.etherscan.io/tx/")

# ── IPFS configuration (Stage 7) ──────────────────────────────────
# Provider selects which off-chain storage backend is used:
#   mock   → local content store (no network, default; ideal for tests)
#   pinata → Pinata pinning service (requires PINATA_JWT)
IPFS_PROVIDER = os.getenv("IPFS_PROVIDER", "mock")
IPFS_GATEWAY_URL = os.getenv("IPFS_GATEWAY_URL", "https://ipfs.io/ipfs/")
PINATA_JWT = os.getenv("PINATA_JWT", "")
PINATA_API_URL = os.getenv("PINATA_API_URL", "https://api.pinata.cloud")

# ── Load ABI ──────────────────────────────────────────────────────
ABI_PATH = ABI_DIR / "ProofOfExistence.json"


def load_abi() -> list:
    """Load the contract ABI from JSON."""
    with open(ABI_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
