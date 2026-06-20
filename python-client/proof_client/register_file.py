"""
register_file.py — Register a file on-chain

Full flow: compute hash → call contract register → persist evidence
(JSON + SQLite).
"""

import sys
from pathlib import Path

from proof_client.config import CONTRACT_ADDRESS, EXPLORER_TX_URL
from proof_client.hash_file import sha256_hash
from proof_client.wallet import get_address
from proof_client.contract_client import register_hash
from proof_client.evidence_schema import EvidenceRecord
from proof_client.evidence_store import save_evidence
from proof_client import evidence_repository as repo


def register_file(file_path: str, uri: str | None = None) -> EvidenceRecord:
    """
    Register a single file on the blockchain.

    Args:
        file_path: Path to the file.
        uri: Optional file identifier; defaults to sepolia://<filename>.

    Returns:
        EvidenceRecord instance.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    file_name = path.name
    if uri is None:
        uri = f"sepolia://{file_name}"

    # 1) Compute hash
    file_hash = sha256_hash(path)
    print(f"📄 File:    {file_name}")
    print(f"🔑 SHA-256: {file_hash}")

    # 2) Call contract
    print("⏳ Submitting to Sepolia...")
    result = register_hash(file_hash, uri)
    print("✅ Transaction successful!")
    print(f"   Tx Hash: 0x{result['tx_hash']}")
    print(f"   Block:   {result['block_number']}")
    print(f"   Gas:     {result['gas_used']}")

    # 3) Build evidence record
    record = EvidenceRecord(
        file_name=file_name,
        file_hash=file_hash,
        uri=uri,
        tx_hash=result["tx_hash"],
        block_number=result["block_number"],
        gas_used=result["gas_used"],
        owner=get_address(),
        status=result["status"],
        contract_address=CONTRACT_ADDRESS,
        explorer_tx_url=EXPLORER_TX_URL,
    )

    # 4) Dual-write: JSON + SQLite
    save_evidence(record)
    repo.insert(record)

    print(f"🔗 View on explorer: {record.explorer_link}")
    return record


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m proof_client.register_file <file_path> [uri]")
        sys.exit(1)

    fpath = sys.argv[1]
    file_uri = sys.argv[2] if len(sys.argv) > 2 else None
    register_file(fpath, file_uri)
