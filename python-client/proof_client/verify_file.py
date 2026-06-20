"""
verify_file.py — Verify whether a file has been registered on-chain

Full flow: compute hash → call contract verify → compare with local evidence.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from proof_client.hash_file import sha256_hash
from proof_client.contract_client import verify_hash
from proof_client.evidence_store import load_evidence


def verify_file(file_path: str) -> dict:
    """
    Verify whether a file has been registered on the blockchain.

    Args:
        file_path: Path to the file.

    Returns:
        Dict with verification results:
        - registered: whether the file is registered
        - file_hash: computed file hash
        - chain_data: on-chain data (owner, timestamp, uri)
        - local_evidence: local evidence record if found
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # 1) Compute current file hash
    file_hash = sha256_hash(path)
    print(f"📄 File:    {path.name}")
    print(f"🔑 SHA-256: {file_hash}")

    # 2) Query on-chain record
    print("🔍 Querying on-chain record...")
    chain_data = verify_hash(file_hash)

    if not chain_data["registered"]:
        print("❌ This file hash has not been registered on-chain.")
        return {
            "registered": False,
            "file_hash": file_hash,
            "chain_data": chain_data,
            "local_evidence": None,
        }

    # 3) Display on-chain information
    ts = chain_data["timestamp"]
    ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    print("✅ File is registered on-chain!")
    print(f"   Owner:     {chain_data['owner']}")
    print(f"   Timestamp: {ts} ({ts_str})")
    print(f"   URI:       {chain_data['uri']}")

    # 4) Try to load local evidence
    local = load_evidence(file_hash)
    if local:
        print(f"📋 Local evidence: found (Tx: 0x{local.tx_hash[:16]}...)")
    else:
        print("📋 Local evidence: not found")

    return {
        "registered": True,
        "file_hash": file_hash,
        "chain_data": chain_data,
        "local_evidence": local,
    }


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m proof_client.verify_file <file_path>")
        sys.exit(1)

    verify_file(sys.argv[1])
