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

# Ensure required directories exist
for d in (WORKS_DIR, EVIDENCE_DIR, REPORTS_DIR, PACKAGES_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Blockchain configuration ──────────────────────────────────────
RPC_URL = os.getenv("RPC_URL", "")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
CHAIN_ID = int(os.getenv("CHAIN_ID", "11155111"))
EXPLORER_TX_URL = os.getenv("EXPLORER_TX_URL", "https://sepolia.etherscan.io/tx/")

# ── Load ABI ──────────────────────────────────────────────────────
ABI_PATH = ABI_DIR / "ProofOfExistence.json"


def load_abi() -> list:
    """Load the contract ABI from JSON."""
    with open(ABI_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
