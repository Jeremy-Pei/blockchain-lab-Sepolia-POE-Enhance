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

# Stage 8: local encryption working directories
ENCRYPTED_DIR = PROJECT_ROOT / "encrypted"
DECRYPTED_DIR = PROJECT_ROOT / "decrypted"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"

# Stage 9: batch Merkle registration directories
BATCH_EVIDENCE_DIR = EVIDENCE_DIR / "batches"
BATCH_PACKAGES_DIR = PACKAGES_DIR / "batches"
BATCH_REPORTS_DIR = REPORTS_DIR / "batches"

# Stage 10: FastAPI service working directories
#   UPLOADS_DIR  → files received via multipart upload are saved here
#   API_TEMP_DIR → scratch space for transient API artifacts (proofs, etc.)
UPLOADS_DIR = PROJECT_ROOT / "uploads"
API_TEMP_DIR = PROJECT_ROOT / "api_tmp"

# Ensure required directories exist
for d in (
    WORKS_DIR,
    EVIDENCE_DIR,
    REPORTS_DIR,
    PACKAGES_DIR,
    MOCK_IPFS_DIR,
    ENCRYPTED_DIR,
    DECRYPTED_DIR,
    DOWNLOADS_DIR,
    BATCH_EVIDENCE_DIR,
    BATCH_PACKAGES_DIR,
    BATCH_REPORTS_DIR,
    UPLOADS_DIR,
    API_TEMP_DIR,
):
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

# ── Encryption configuration (Stage 8) ────────────────────────────
# AES-256-GCM authenticated encryption with a password-derived key.
# Files are encrypted locally BEFORE upload to IPFS so that public
# pinning never exposes the plaintext. The password/key is never stored.
ENCRYPTION_ALGORITHM = "AES-256-GCM"
ENCRYPTION_KDF = "PBKDF2-HMAC-SHA256"
ENCRYPTION_PBKDF2_ITERATIONS = int(
    os.getenv("ENCRYPTION_PBKDF2_ITERATIONS", "600000")
)
ENCRYPTION_SALT_BYTES = 16  # 128-bit salt
ENCRYPTION_NONCE_BYTES = 12  # 96-bit nonce, the AES-GCM standard

# ── Load ABI ──────────────────────────────────────────────────────
ABI_PATH = ABI_DIR / "ProofOfExistence.json"


def load_abi() -> list:
    """Load the contract ABI from JSON."""
    with open(ABI_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
