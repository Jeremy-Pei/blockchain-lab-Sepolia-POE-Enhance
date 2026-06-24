"""
encrypt_file.py — Encrypt a file locally with AES-256-GCM (Stage 8)

Produces two outputs next to each other:
  <output>                  ← the ciphertext
  <output>.metadata.json    ← public KDF/cipher parameters (salt, nonce, …)

The password is read interactively (never from the command line / argv, so it
cannot leak into shell history or process listings) and is NEVER written to
disk. Without the password the ciphertext cannot be decrypted by this system.

CLI:
  python -m proof_client.encrypt_file works/my_paper.pdf \
      --output encrypted/my_paper.pdf.enc
"""

import argparse
import json
import sys
from getpass import getpass
from pathlib import Path

from proof_client.config import ENCRYPTED_DIR
from proof_client.crypto_utils import EncryptionResult, encrypt_file


def _default_output(input_path: Path) -> Path:
    """Default ciphertext path: encrypted/<name>.enc."""
    return ENCRYPTED_DIR / f"{input_path.name}.enc"


def metadata_path_for(encrypted_path: Path) -> Path:
    """Return the sidecar metadata path for an encrypted file."""
    return encrypted_path.with_name(encrypted_path.name + ".metadata.json")


def write_metadata(result: EncryptionResult, encrypted_path: Path) -> Path:
    """Write the .metadata.json sidecar (no secrets) and return its path."""
    meta_path = metadata_path_for(encrypted_path)
    meta_path.write_text(
        json.dumps(result.to_metadata(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return meta_path


def prompt_new_password() -> str:
    """Prompt for a password twice and confirm they match."""
    pw = getpass("Enter encryption password: ")
    if not pw:
        raise ValueError("Password must not be empty.")
    confirm = getpass("Confirm encryption password: ")
    if pw != confirm:
        raise ValueError("Passwords do not match.")
    return pw


def run_encrypt(input_path: str, output: str | None, password: str) -> EncryptionResult:
    """Encrypt input_path, write ciphertext + metadata, and print a summary."""
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")

    out = Path(output) if output else _default_output(src)
    result = encrypt_file(src, out, password)
    meta_path = write_metadata(result, out)

    print(f"📄 Original file:    {result.original_path}")
    print(f"🔒 Encrypted file:   {result.encrypted_path}")
    print(f"🔑 Original SHA-256: {result.original_sha256}")
    print(f"🔑 Encrypted SHA-256:{result.encrypted_sha256}")
    print(f"🧮 Algorithm:        {result.algorithm}")
    print(f"🧂 KDF:              {result.kdf} ({result.kdf_iterations} iters)")
    print(f"🗂️  Metadata:         {meta_path}")
    print("ℹ️  The password is NOT stored. Keep it safe — it cannot be recovered.")
    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.encrypt_file",
        description="Encrypt a file locally with AES-256-GCM before sharing/upload.",
    )
    parser.add_argument("file_path", help="Path to the plaintext file to encrypt")
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Ciphertext output path (default: encrypted/<name>.enc)",
    )
    return parser.parse_args(argv)


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    try:
        password = prompt_new_password()
        run_encrypt(args.file_path, args.output, password)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)
