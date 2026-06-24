"""
crypto_utils.py — Local file encryption primitives (Stage 8)

Provides authenticated, password-based file encryption so that a sensitive
work can be encrypted locally BEFORE it is uploaded to public IPFS. Public
IPFS is world-readable; pinning a raw file exposes its bytes to anyone who
learns the CID. Stage 8 closes that gap: only ciphertext ever leaves the
machine, while the blockchain still anchors the ORIGINAL file's SHA-256.

Scheme:
    Key derivation : PBKDF2-HMAC-SHA256 (600k iterations, 32-byte key)
    Encryption     : AES-256-GCM (authenticated; detects wrong password
                     and any ciphertext tampering on decrypt)
    salt           : 16 bytes, random per file
    nonce          : 12 bytes, random per file (AES-GCM standard)

Critical invariants:
  * The password and the derived key are NEVER returned in metadata,
    written to disk, logged, or persisted anywhere.
  * The salt and nonce are NOT secret — they are stored in the metadata so
    a holder of the password can re-derive the key and decrypt.
  * original_sha256 (of the plaintext) stays the primary evidence hash;
    encrypted_sha256 (of the ciphertext) only identifies the uploaded blob.
"""

import hashlib
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from proof_client.config import (
    ENCRYPTION_ALGORITHM,
    ENCRYPTION_KDF,
    ENCRYPTION_NONCE_BYTES,
    ENCRYPTION_PBKDF2_ITERATIONS,
    ENCRYPTION_SALT_BYTES,
)

# AES-256 uses a 256-bit (32-byte) key.
_AES_KEY_BYTES = 32


class DecryptionError(Exception):
    """Raised when decryption fails (wrong password or corrupted ciphertext)."""


# ══════════════════════════════════════════════════════════════════
# Result data structure
# ══════════════════════════════════════════════════════════════════

@dataclass
class EncryptionResult:
    """The outcome of encrypting a single file.

    NOTE: deliberately carries NO password and NO key — only the public
    parameters (salt, nonce, algorithm) needed to decrypt later given the
    correct password.
    """

    original_path: str
    encrypted_path: str
    original_sha256: str
    encrypted_sha256: str
    algorithm: str
    kdf: str
    kdf_iterations: int
    salt_hex: str
    nonce_hex: str
    encrypted_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serialisable dict (no secrets included)."""
        return asdict(self)

    def to_metadata(self) -> Dict[str, Any]:
        """Return the sidecar metadata dict written next to the ciphertext."""
        return {
            "algorithm": self.algorithm,
            "kdf": self.kdf,
            "kdf_iterations": self.kdf_iterations,
            "salt_hex": self.salt_hex,
            "nonce_hex": self.nonce_hex,
            "original_sha256": self.original_sha256,
            "encrypted_sha256": self.encrypted_sha256,
            "encrypted_at_utc": self.encrypted_at_utc,
        }


# ══════════════════════════════════════════════════════════════════
# Pure helpers
# ══════════════════════════════════════════════════════════════════

def _sha256_bytes(data: bytes) -> str:
    """Return the 0x-prefixed SHA-256 hex digest of a bytes object."""
    return "0x" + hashlib.sha256(data).hexdigest()


def _now_utc() -> str:
    """Return the current UTC time as an ISO-8601 'Z' string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_salt(n_bytes: int = ENCRYPTION_SALT_BYTES) -> bytes:
    """Return a cryptographically random salt."""
    return os.urandom(n_bytes)


def generate_nonce(n_bytes: int = ENCRYPTION_NONCE_BYTES) -> bytes:
    """Return a cryptographically random AES-GCM nonce."""
    return os.urandom(n_bytes)


def derive_key_from_password(
    password: str,
    salt: bytes,
    iterations: int = ENCRYPTION_PBKDF2_ITERATIONS,
) -> bytes:
    """
    Derive a 32-byte AES-256 key from a password and salt via PBKDF2-HMAC-SHA256.

    The same (password, salt, iterations) always yields the same key, which is
    exactly how a verifier re-derives the key to decrypt. Different salts yield
    different keys even for the same password.
    """
    if not password:
        raise ValueError("password must not be empty")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_AES_KEY_BYTES,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))


# ══════════════════════════════════════════════════════════════════
# Encrypt / decrypt
# ══════════════════════════════════════════════════════════════════

def encrypt_file(
    input_path: str | Path,
    output_path: str | Path,
    password: str,
    iterations: int = ENCRYPTION_PBKDF2_ITERATIONS,
) -> EncryptionResult:
    """
    Encrypt input_path to output_path with AES-256-GCM.

    Args:
        input_path: Plaintext file to encrypt.
        output_path: Destination for the ciphertext (.enc).
        password: User-supplied password (never stored).
        iterations: PBKDF2 iteration count.

    Returns:
        EncryptionResult with hashes and the public KDF/cipher parameters.
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")

    plaintext = src.read_bytes()
    original_sha256 = _sha256_bytes(plaintext)

    salt = generate_salt()
    nonce = generate_nonce()
    key = derive_key_from_password(password, salt, iterations)

    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(ciphertext)

    return EncryptionResult(
        original_path=str(src),
        encrypted_path=str(out),
        original_sha256=original_sha256,
        encrypted_sha256=_sha256_bytes(ciphertext),
        algorithm=ENCRYPTION_ALGORITHM,
        kdf=ENCRYPTION_KDF,
        kdf_iterations=iterations,
        salt_hex=salt.hex(),
        nonce_hex=nonce.hex(),
        encrypted_at_utc=_now_utc(),
    )


def decrypt_file(
    encrypted_path: str | Path,
    output_path: str | Path,
    password: str,
    metadata: Dict[str, Any],
) -> Path:
    """
    Decrypt encrypted_path to output_path using parameters from metadata.

    Args:
        encrypted_path: Ciphertext file (.enc).
        output_path: Destination for the recovered plaintext.
        password: User-supplied password.
        metadata: Dict carrying salt_hex, nonce_hex and kdf_iterations.

    Returns:
        Path to the decrypted output file.

    Raises:
        DecryptionError: If the password is wrong or the ciphertext is
            corrupted/tampered (AES-GCM authentication failure).
    """
    src = Path(encrypted_path)
    if not src.exists():
        raise FileNotFoundError(f"Encrypted file not found: {src}")

    try:
        salt = bytes.fromhex(metadata["salt_hex"])
        nonce = bytes.fromhex(metadata["nonce_hex"])
    except (KeyError, ValueError) as exc:
        raise DecryptionError(f"Invalid or incomplete encryption metadata: {exc}")

    iterations = int(metadata.get("kdf_iterations", ENCRYPTION_PBKDF2_ITERATIONS))
    key = derive_key_from_password(password, salt, iterations)

    ciphertext = src.read_bytes()
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    except InvalidTag:
        raise DecryptionError(
            "Decryption failed: invalid password or corrupted encrypted file."
        )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(plaintext)
    return out


def sha256_of_bytes(data: bytes) -> str:
    """Public wrapper: 0x-prefixed SHA-256 of a bytes object."""
    return _sha256_bytes(data)
