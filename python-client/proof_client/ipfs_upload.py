"""
ipfs_upload.py — Upload a file to IPFS and print its CID (Stage 7)

CLI:
  python -m proof_client.ipfs_upload <file_path> [--provider mock|pinata]

This does NOT touch the blockchain — it only stores the file off-chain and
reports the resulting content identifier. Use register_file --upload-ipfs to
do both in one step.
"""

import argparse
import sys

from proof_client.config import IPFS_PROVIDER
from proof_client.ipfs_client import IPFSUploadResult, get_client


def upload_to_ipfs(file_path: str, provider: str | None = None) -> IPFSUploadResult:
    """Upload a file to IPFS via the selected provider and return the result."""
    client = get_client(provider)
    result = client.upload_file(file_path)

    print(f"📄 File:        {file_path}")
    print(f"🔑 SHA-256:     {result.file_sha256}")
    print(f"🌀 CID:         {result.cid}")
    print(f"🔗 IPFS URI:    {result.uri}")
    print(f"🌐 Gateway URL: {result.gateway_url}")
    print(f"📦 Provider:    {result.provider}")
    return result


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.ipfs_upload",
        description="Upload a file to IPFS and print its CID.",
    )
    parser.add_argument("file_path", help="Path to the file to upload")
    parser.add_argument(
        "--provider",
        default=None,
        help=f"IPFS provider (default: {IPFS_PROVIDER})",
    )
    args = parser.parse_args()

    try:
        upload_to_ipfs(args.file_path, args.provider)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)
