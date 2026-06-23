"""
ipfs_download.py — Download a file from IPFS by CID (Stage 7)

CLI:
  python -m proof_client.ipfs_download <cid> --output downloads/my_file
  python -m proof_client.ipfs_download ipfs://<cid> -o downloads/my_file
"""

import argparse
import sys
from pathlib import Path

from proof_client.config import IPFS_PROVIDER
from proof_client.ipfs_client import get_client, parse_cid_from_uri


def download_from_ipfs(
    cid: str, output_path: str | Path, provider: str | None = None
) -> Path:
    """Download a CID from IPFS via the selected provider to output_path."""
    client = get_client(provider)
    cid = parse_cid_from_uri(cid)
    out = client.download_file(cid, output_path)

    print(f"🌀 CID:      {cid}")
    print(f"💾 Saved to: {out}")
    print(f"📦 Provider: {client.provider}")
    return out


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.ipfs_download",
        description="Download a file from IPFS by CID.",
    )
    parser.add_argument("cid", help="Content identifier (CID) or ipfs:// URI")
    parser.add_argument(
        "-o", "--output", required=True, help="Path to write the downloaded file"
    )
    parser.add_argument(
        "--provider",
        default=None,
        help=f"IPFS provider (default: {IPFS_PROVIDER})",
    )
    args = parser.parse_args()

    try:
        download_from_ipfs(args.cid, args.output, args.provider)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)
