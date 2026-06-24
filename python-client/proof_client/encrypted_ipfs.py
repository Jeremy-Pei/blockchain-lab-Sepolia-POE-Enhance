"""
encrypted_ipfs.py — Encrypt-then-upload to IPFS (Stage 8)

Combines Stage 8 encryption with the Stage 7 IPFS layer:

    original file
      → SHA-256 (original)          ← stays the primary evidence hash
      → encrypt locally (AES-256-GCM)
      → SHA-256 (ciphertext)
      → upload CIPHERTEXT to IPFS
      → ipfs://<cid> of the ciphertext

Only ciphertext is ever uploaded, so a public gateway never exposes the
plaintext. The password is never persisted; only the public salt/nonce/kdf
parameters travel in the metadata so a holder of the password can decrypt.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from proof_client.config import ENCRYPTED_DIR
from proof_client.crypto_utils import EncryptionResult, encrypt_file
from proof_client.ipfs_client import IPFSUploadResult, get_client


def _encrypted_output(file_path: Path, output_dir: Optional[Path]) -> Path:
    """Resolve the ciphertext output path for a given input file."""
    out_dir = Path(output_dir) if output_dir else ENCRYPTED_DIR
    return out_dir / f"{file_path.name}.enc"


def encrypt_and_upload_to_ipfs(
    file_path: str | Path,
    password: str,
    ipfs_provider: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Encrypt a file locally, then upload only the ciphertext to IPFS.

    Args:
        file_path: Plaintext file to protect.
        password: Encryption password (never stored).
        ipfs_provider: 'mock' / 'pinata' (defaults to IPFS_PROVIDER).
        output_dir: Where to write the ciphertext (default: encrypted/).

    Returns:
        A dict carrying the original/ciphertext hashes, the encryption
        parameters, and the IPFS pointers for the uploaded ciphertext.
    """
    src = Path(file_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")

    enc_out = _encrypted_output(src, output_dir)
    enc: EncryptionResult = encrypt_file(src, enc_out, password)

    client = get_client(ipfs_provider)
    upload: IPFSUploadResult = client.upload_file(enc_out)

    return {
        "original_file_name": src.name,
        "original_sha256": enc.original_sha256,
        "encrypted_sha256": enc.encrypted_sha256,
        "encrypted_file_path": enc.encrypted_path,
        "encrypted_file_name": enc_out.name,
        "algorithm": enc.algorithm,
        "kdf": enc.kdf,
        "kdf_iterations": enc.kdf_iterations,
        "salt_hex": enc.salt_hex,
        "nonce_hex": enc.nonce_hex,
        "encrypted_at_utc": enc.encrypted_at_utc,
        "encrypted_ipfs_cid": upload.cid,
        "encrypted_ipfs_uri": upload.uri,
        "encrypted_ipfs_gateway_url": upload.gateway_url,
        "encrypted_ipfs_provider": upload.provider,
        "encrypted_ipfs_uploaded_at": upload.uploaded_at_utc,
        # The IPFS layer's own hash of what it stored == the ciphertext hash.
        "ipfs_sha256": upload.file_sha256,
    }
