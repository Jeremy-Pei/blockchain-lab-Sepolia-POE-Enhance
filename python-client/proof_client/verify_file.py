"""
verify_file.py — Verify whether a file has been registered on-chain

Full flow: compute hash → call contract verify → compare with local evidence.

Stage 12: accepts --network / network_key.  Priority for which network to
query: (1) explicit --network arg, (2) network_key stored on local evidence
record, (3) DEFAULT_NETWORK env var.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from proof_client.hash_file import sha256_hash
from proof_client.contract_client import verify_hash
from proof_client.evidence_store import load_evidence


def verify_file(file_path: str, network_key: str | None = None) -> dict:
    """
    Verify whether a file has been registered on the blockchain.

    Args:
        file_path: Path to the file.
        network_key: Optional network to query.  When None the function first
                     checks the local evidence record's network_key, then falls
                     back to the DEFAULT_NETWORK env var.

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

    # 2) Try to load local evidence first so we can pick the right network
    local = load_evidence(file_hash)

    # Network resolution priority: explicit arg > local record > default
    resolved_network = network_key
    if resolved_network is None and local is not None:
        resolved_network = getattr(local, "network_key", "") or None
    # If still None, contract_client will use DEFAULT_NETWORK

    # 3) Query on-chain record
    print("🔍 Querying on-chain record...")
    chain_data = verify_hash(file_hash, network_key=resolved_network)

    if not chain_data["registered"]:
        print("❌ This file hash has not been registered on-chain.")
        return {
            "registered": False,
            "file_hash": file_hash,
            "chain_data": chain_data,
            "local_evidence": None,
        }

    # 4) Display on-chain information
    ts = chain_data["timestamp"]
    ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    print("✅ File is registered on-chain!")
    print(f"   Owner:     {chain_data['owner']}")
    print(f"   Timestamp: {ts} ({ts_str})")
    print(f"   URI:       {chain_data['uri']}")

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


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.verify_file",
        description="Verify whether a file has been registered on the blockchain.",
    )
    parser.add_argument("file_path", help="Path to the file to verify")
    parser.add_argument(
        "--network",
        default=None,
        help="Network key to query, e.g. anvil, sepolia, base-sepolia "
        "(default: network from local evidence, then DEFAULT_NETWORK)",
    )
    return parser.parse_args(argv)


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    verify_file(args.file_path, network_key=args.network)
