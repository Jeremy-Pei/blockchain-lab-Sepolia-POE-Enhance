"""
verify_ipfs.py — Verify IPFS content against an evidence hash (Stage 7)

Downloads a file from IPFS by CID, recomputes its SHA-256, and compares it
to the expected hash. This closes the verification loop:

    IPFS file → SHA-256 → compare with evidence file_hash → query contract

CLI:
  # Verify a specific CID against an expected hash
  python -m proof_client.verify_ipfs --cid <cid> --expected-hash <0x...>

  # Look up the CID + expected hash from stored evidence by file hash
  python -m proof_client.verify_ipfs --hash <0x...>
"""

import argparse
import sys
import tempfile
from pathlib import Path

from proof_client.config import IPFS_PROVIDER
from proof_client.evidence_store import load_evidence
from proof_client.hash_file import sha256_hash
from proof_client.ipfs_client import get_client, parse_cid_from_uri


def _normalise(h: str) -> str:
    """Lower-case and 0x-prefix a hash for comparison."""
    h = (h or "").lower()
    return h if h.startswith("0x") else f"0x{h}"


def verify_ipfs(cid: str, expected_hash: str, provider: str | None = None) -> dict:
    """
    Download a CID and compare its SHA-256 against expected_hash.

    Returns a dict with:
        match, cid, provider, expected_hash, actual_hash
    """
    cid = parse_cid_from_uri(cid)
    client = get_client(provider)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ipfs_downloaded_file"
        client.download_file(cid, out)
        actual_hash = sha256_hash(out)

    expected = _normalise(expected_hash)
    actual = _normalise(actual_hash)
    return {
        "match": expected == actual,
        "cid": cid,
        "provider": client.provider,
        "expected_hash": expected,
        "actual_hash": actual,
    }


def verify_ipfs_by_hash(file_hash: str) -> dict | None:
    """
    Look up stored evidence by file_hash, then verify its IPFS content.

    Returns the verify_ipfs result dict, or None if no evidence/CID exists.
    """
    record = load_evidence(file_hash)
    if record is None:
        print(f"❌ No evidence found for hash {file_hash}")
        return None
    if not record.ipfs_cid:
        print(f"❌ Evidence for {file_hash} has no IPFS CID recorded.")
        return None

    provider = record.ipfs_provider or None
    # Map stored provider label back to a factory name.
    if provider in ("mock-ipfs", "local-mock"):
        provider = "mock"
    return verify_ipfs(record.ipfs_cid, record.file_hash, provider)


def _print_result(result: dict) -> None:
    print(f"🌀 CID:           {result['cid']}")
    print(f"📦 Provider:      {result['provider']}")
    print(f"🔑 Expected hash: {result['expected_hash']}")
    print(f"🔑 Actual hash:   {result['actual_hash']}")
    if result["match"]:
        print("✅ MATCH — IPFS content matches the evidence hash.")
    else:
        print("❌ MISMATCH — IPFS content does NOT match the evidence hash!")


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.verify_ipfs",
        description="Verify IPFS content against an evidence SHA-256 hash.",
    )
    parser.add_argument("--cid", help="Content identifier (CID) or ipfs:// URI")
    parser.add_argument("--expected-hash", help="Expected 0x-prefixed SHA-256")
    parser.add_argument("--hash", help="Look up CID + expected hash from evidence")
    parser.add_argument(
        "--provider", default=None, help=f"IPFS provider (default: {IPFS_PROVIDER})"
    )
    args = parser.parse_args()

    try:
        if args.hash:
            result = verify_ipfs_by_hash(args.hash)
            if result is None:
                sys.exit(1)
        elif args.cid and args.expected_hash:
            result = verify_ipfs(args.cid, args.expected_hash, args.provider)
        else:
            parser.error("Provide either --hash, or both --cid and --expected-hash")

        _print_result(result)
        sys.exit(0 if result["match"] else 1)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)
