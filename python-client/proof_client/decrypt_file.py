"""
decrypt_file.py — Decrypt an AES-256-GCM encrypted file (Stage 8)

Reads the ciphertext and its .metadata.json sidecar, prompts for the password,
re-derives the key, and writes the recovered plaintext. If the metadata records
the expected original SHA-256, the recovered file's hash is compared against it
and the match is reported.

CLI:
  python -m proof_client.decrypt_file encrypted/my_paper.pdf.enc \
      --metadata encrypted/my_paper.pdf.enc.metadata.json \
      --output decrypted/my_paper.pdf
"""

import argparse
import json
import sys
from getpass import getpass
from pathlib import Path

from proof_client.config import DECRYPTED_DIR
from proof_client.crypto_utils import DecryptionError, decrypt_file, sha256_of_bytes


def _default_metadata(encrypted_path: Path) -> Path:
    """Default sidecar metadata path: <encrypted>.metadata.json."""
    return encrypted_path.with_name(encrypted_path.name + ".metadata.json")


def _default_output(encrypted_path: Path) -> Path:
    """Default plaintext path: decrypted/<name without .enc>."""
    name = encrypted_path.name
    if name.endswith(".enc"):
        name = name[: -len(".enc")]
    return DECRYPTED_DIR / name


def run_decrypt(
    encrypted: str,
    metadata: str | None,
    output: str | None,
    password: str,
) -> Path:
    """Decrypt the file and print a verification summary."""
    enc_path = Path(encrypted)
    if not enc_path.exists():
        raise FileNotFoundError(f"Encrypted file not found: {enc_path}")

    meta_path = Path(metadata) if metadata else _default_metadata(enc_path)
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    out_path = Path(output) if output else _default_output(enc_path)
    result = decrypt_file(enc_path, out_path, password, meta)

    actual = sha256_of_bytes(result.read_bytes())
    expected = meta.get("original_sha256", "")

    print(f"🔓 Decrypted file:          {result}")
    print(f"🔑 SHA-256:                 {actual}")
    if expected:
        match = actual.lower() == expected.lower()
        print(f"🔑 Expected original SHA-256:{expected}")
        print(f"{'✅' if match else '❌'} Match: {'YES' if match else 'NO'}")
    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.decrypt_file",
        description="Decrypt an AES-256-GCM encrypted file using its metadata.",
    )
    parser.add_argument("encrypted_path", help="Path to the .enc ciphertext file")
    parser.add_argument(
        "--metadata",
        "-m",
        default=None,
        help="Metadata JSON (default: <encrypted>.metadata.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Plaintext output path (default: decrypted/<name without .enc>)",
    )
    return parser.parse_args(argv)


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    try:
        password = getpass("Enter decryption password: ")
        run_decrypt(args.encrypted_path, args.metadata, args.output, password)
    except DecryptionError as exc:
        print(f"❌ {exc}")
        sys.exit(1)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)
