"""
hash_file.py — Compute SHA-256 hash of a file

Reads file contents and returns a 0x-prefixed hex digest compatible
with the bytes32 format used in the Solidity contract.
"""

import hashlib
import sys
from pathlib import Path


def sha256_hash(file_path: str | Path) -> str:
    """
    Compute the SHA-256 hash of a file.

    Args:
        file_path: Path to the file to hash.

    Returns:
        64-character hex string prefixed with 0x.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)

    return "0x" + h.hexdigest()


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m proof_client.hash_file <file_path>")
        sys.exit(1)

    target = sys.argv[1]
    digest = sha256_hash(target)
    print(f"File:   {target}")
    print(f"SHA-256: {digest}")
