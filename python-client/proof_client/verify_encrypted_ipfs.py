"""
verify_encrypted_ipfs.py — Verify an encrypted IPFS record end-to-end (Stage 8)

Closes the privacy-preserving verification loop:

    encrypted IPFS file
      → download ciphertext by CID
      → (optional) confirm ciphertext SHA-256 == encrypted_file_hash
      → decrypt with the password + stored salt/nonce/kdf
      → recompute decrypted SHA-256
      → compare with evidence.file_hash (the ORIGINAL plaintext hash)

Two modes:

  # Look everything up from stored evidence by the original file hash
  python -m proof_client.verify_encrypted_ipfs --hash 0x<original_file_hash>

  # Provide the pieces manually
  python -m proof_client.verify_encrypted_ipfs \
      --cid <encrypted_cid> \
      --expected-hash 0x<original_file_hash> \
      --metadata encrypted/my_paper.pdf.enc.metadata.json
"""

import argparse
import json
import sys
import tempfile
from getpass import getpass
from pathlib import Path
from typing import Any, Dict, Optional

from proof_client.config import IPFS_PROVIDER
from proof_client.crypto_utils import DecryptionError, decrypt_file, sha256_of_bytes
from proof_client.evidence_store import load_evidence
from proof_client.ipfs_client import get_client, parse_cid_from_uri


def _normalise(h: str) -> str:
    """Lower-case and 0x-prefix a hash for comparison."""
    h = (h or "").lower()
    return h if h.startswith("0x") else f"0x{h}"


def _map_provider(provider: str | None) -> str | None:
    """Map a stored provider label back to a factory name."""
    if provider in ("mock-ipfs", "local-mock"):
        return "mock"
    return provider or None


def verify_encrypted_ipfs(
    cid: str,
    expected_hash: str,
    metadata: Dict[str, Any],
    password: str,
    provider: Optional[str] = None,
    expected_encrypted_hash: str = "",
) -> dict:
    """
    Download a ciphertext CID, decrypt it, and compare the recovered hash.

    Returns a dict with the comparison results. Never raises on a hash
    mismatch — only on download / decryption failure.
    """
    cid = parse_cid_from_uri(cid)
    client = get_client(provider)

    with tempfile.TemporaryDirectory() as tmp:
        enc_out = Path(tmp) / "downloaded.enc"
        client.download_file(cid, enc_out)
        downloaded_encrypted_hash = sha256_of_bytes(enc_out.read_bytes())

        dec_out = Path(tmp) / "decrypted.bin"
        # Raises DecryptionError on wrong password / tampered ciphertext.
        decrypt_file(enc_out, dec_out, password, metadata)
        decrypted_hash = sha256_of_bytes(dec_out.read_bytes())

    expected = _normalise(expected_hash)
    actual = _normalise(decrypted_hash)

    ciphertext_ok = True
    if expected_encrypted_hash:
        ciphertext_ok = (
            _normalise(downloaded_encrypted_hash) == _normalise(expected_encrypted_hash)
        )

    return {
        "match": expected == actual and ciphertext_ok,
        "cid": cid,
        "provider": client.provider,
        "expected_original_hash": expected,
        "decrypted_hash": actual,
        "downloaded_encrypted_hash": _normalise(downloaded_encrypted_hash),
        "expected_encrypted_hash": _normalise(expected_encrypted_hash)
        if expected_encrypted_hash
        else "",
        "ciphertext_hash_ok": ciphertext_ok,
    }


def verify_encrypted_ipfs_by_hash(file_hash: str, password: str) -> dict | None:
    """
    Look up stored evidence by original file_hash, then verify its encrypted
    IPFS content. Returns the result dict, or None if evidence is missing or
    is not an encrypted record.
    """
    record = load_evidence(file_hash)
    if record is None:
        print(f"❌ No evidence found for hash {file_hash}")
        return None
    if not record.has_encrypted_ipfs:
        print(f"❌ Evidence for {file_hash} has no encrypted IPFS content.")
        return None

    metadata = {
        "salt_hex": record.encryption_salt_hex,
        "nonce_hex": record.encryption_nonce_hex,
        "kdf_iterations": record.encryption_kdf_iterations,
        "original_sha256": record.file_hash,
    }
    return verify_encrypted_ipfs(
        record.encrypted_ipfs_cid,
        record.file_hash,
        metadata,
        password,
        provider=_map_provider(record.encrypted_ipfs_provider),
        expected_encrypted_hash=record.encrypted_file_hash,
    )


def _print_result(result: dict) -> None:
    print(f"🌀 CID:                         {result['cid']}")
    print(f"📦 Provider:                    {result['provider']}")
    print(f"🔒 Downloaded ciphertext SHA-256: {result['downloaded_encrypted_hash']}")
    if result["expected_encrypted_hash"]:
        mark = "✅" if result["ciphertext_hash_ok"] else "❌"
        print(f"{mark} Expected ciphertext SHA-256:  {result['expected_encrypted_hash']}")
    print(f"🔓 Decrypted SHA-256:           {result['decrypted_hash']}")
    print(f"🔑 Expected original SHA-256:   {result['expected_original_hash']}")
    if result["match"]:
        print("✅ Encrypted IPFS verification: PASSED")
    else:
        print("❌ Encrypted IPFS verification: FAILED")


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.verify_encrypted_ipfs",
        description="Verify encrypted IPFS content against an original SHA-256 hash.",
    )
    parser.add_argument("--hash", help="Original file hash; looks up stored evidence")
    parser.add_argument("--cid", help="Encrypted content identifier (CID) or ipfs:// URI")
    parser.add_argument(
        "--expected-hash", help="Expected 0x-prefixed SHA-256 of the ORIGINAL file"
    )
    parser.add_argument("--metadata", help="Path to the encryption metadata JSON")
    parser.add_argument(
        "--provider", default=None, help=f"IPFS provider (default: {IPFS_PROVIDER})"
    )
    args = parser.parse_args()

    try:
        password = getpass("Enter decryption password: ")
        if args.hash:
            result = verify_encrypted_ipfs_by_hash(args.hash, password)
            if result is None:
                sys.exit(1)
        elif args.cid and args.expected_hash and args.metadata:
            meta = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
            result = verify_encrypted_ipfs(
                args.cid,
                args.expected_hash,
                meta,
                password,
                provider=args.provider,
                expected_encrypted_hash=meta.get("encrypted_sha256", ""),
            )
        else:
            parser.error(
                "Provide either --hash, or all of --cid, --expected-hash and --metadata"
            )

        _print_result(result)
        sys.exit(0 if result["match"] else 1)
    except DecryptionError as exc:
        print(f"❌ {exc}")
        sys.exit(1)
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)
