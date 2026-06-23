"""
ipfs_client.py — Off-chain content-addressed storage layer (Stage 7)

This module adds an IPFS storage layer to the proof-of-existence system.

Important conceptual note:
    file_hash (SHA-256)  proves *which version* of a file was registered.
    IPFS CID             identifies *content* inside the IPFS network.
They are related — both are derived from the bytes of the file — but they
are NOT the same identifier. The SHA-256 remains the primary evidence hash;
the CID is only an off-chain pointer to a retrievable copy of the content.

Backends (selected by IPFS_PROVIDER):
    mock   → MockIPFSClient: a local content store. No network, fully
             deterministic, ideal for automated tests and offline demos.
    pinata → PinataIPFSClient: uploads to the Pinata pinning service.

All clients share one interface (BaseIPFSClient) so callers never need to
know which backend is active.
"""

import hashlib
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from proof_client.config import (
    IPFS_GATEWAY_URL,
    IPFS_PROVIDER,
    MOCK_IPFS_DIR,
    PINATA_API_URL,
    PINATA_JWT,
)

# Public gateways used when building browsable links for evidence packages.
PUBLIC_GATEWAYS = [
    "https://ipfs.io/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
    "https://dweb.link/ipfs/",
]

# Base32 alphabet used by CIDv1 (RFC 4648, lowercase, no padding).
_BASE32_ALPHABET = set("abcdefghijklmnopqrstuvwxyz234567")


# ══════════════════════════════════════════════════════════════════
# Result data structure
# ══════════════════════════════════════════════════════════════════

@dataclass
class IPFSUploadResult:
    """The outcome of uploading a single file to IPFS."""

    cid: str
    uri: str
    gateway_url: str
    provider: str
    uploaded_at_utc: str
    file_sha256: str

    def to_dict(self) -> dict:
        """Convert to a JSON-serialisable dict."""
        return asdict(self)


# ══════════════════════════════════════════════════════════════════
# Pure helpers — CID / URI / gateway formatting
# ══════════════════════════════════════════════════════════════════

def is_valid_cid(cid: str) -> bool:
    """
    Loosely validate an IPFS CID string.

    Accepts:
      - mock CIDs produced by MockIPFSClient (prefix ``mock-``)
      - CIDv0  (``Qm`` + 44 base58 chars, 46 total)
      - CIDv1  (``baf...`` lowercase base32)
    """
    if not cid or not isinstance(cid, str):
        return False

    if cid.startswith("mock-"):
        return len(cid) > len("mock-")

    # CIDv0: base58btc, always starts with "Qm" and is 46 chars long.
    if cid.startswith("Qm"):
        return len(cid) == 46

    # CIDv1: multibase 'b' prefix (base32). Common DAG-PB CIDs start "bafy".
    if cid.startswith("b"):
        return len(cid) >= 20 and all(c in _BASE32_ALPHABET for c in cid)

    return False


def format_ipfs_uri(cid: str) -> str:
    """Return the canonical ``ipfs://<cid>`` URI for a CID."""
    if not cid:
        raise ValueError("Cannot build an ipfs:// URI from an empty CID")
    return f"ipfs://{cid}"


def parse_cid_from_uri(uri: str) -> str:
    """Extract the bare CID from an ``ipfs://<cid>`` URI (or pass a CID through)."""
    if uri.startswith("ipfs://"):
        return uri[len("ipfs://"):]
    return uri


def gateway_url(cid: str, gateway: str | None = None) -> str:
    """
    Build a browsable HTTP gateway URL for a CID.

    Args:
        cid: The content identifier.
        gateway: Gateway base (defaults to IPFS_GATEWAY_URL from config).
    """
    base = (gateway or IPFS_GATEWAY_URL).rstrip("/")
    return f"{base}/{cid}"


def gateway_urls(cid: str) -> list[str]:
    """Return browsable URLs for a CID across several public gateways."""
    return [gateway_url(cid, gw) for gw in PUBLIC_GATEWAYS]


def _sha256_bytes(data: bytes) -> str:
    """Return the 0x-prefixed SHA-256 hex digest of a bytes object."""
    return "0x" + hashlib.sha256(data).hexdigest()


def _now_utc() -> str:
    """Return the current UTC time as an ISO-8601 'Z' string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ══════════════════════════════════════════════════════════════════
# Client interface + implementations
# ══════════════════════════════════════════════════════════════════

class BaseIPFSClient:
    """Abstract IPFS client interface shared by all backends."""

    provider: str = "base"

    def upload_file(self, file_path: str | Path) -> IPFSUploadResult:
        raise NotImplementedError

    def download_file(self, cid: str, output_path: str | Path) -> Path:
        raise NotImplementedError

    def gateway_url(self, cid: str) -> str:
        """Browsable gateway URL for a CID (uses the configured gateway)."""
        return gateway_url(cid)


class MockIPFSClient(BaseIPFSClient):
    """
    A local, network-free IPFS stand-in.

    Files are stored under MOCK_IPFS_DIR keyed by a deterministic,
    content-derived mock CID. Because the CID is derived from the file
    bytes, identical content always yields the same CID — mirroring the
    content-addressing property of real IPFS, which is exactly what the
    tests and offline demos need.
    """

    provider = "mock-ipfs"

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = Path(storage_dir) if storage_dir else MOCK_IPFS_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def make_cid(content: bytes) -> str:
        """Derive a deterministic mock CID from file content."""
        return "mock-" + hashlib.sha256(content).hexdigest()[:46]

    def upload_file(self, file_path: str | Path) -> IPFSUploadResult:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = path.read_bytes()
        cid = self.make_cid(content)

        # Store the content under the CID so download_file can retrieve it.
        (self.storage_dir / cid).write_bytes(content)

        return IPFSUploadResult(
            cid=cid,
            uri=format_ipfs_uri(cid),
            gateway_url=gateway_url(cid),
            provider=self.provider,
            uploaded_at_utc=_now_utc(),
            file_sha256=_sha256_bytes(content),
        )

    def download_file(self, cid: str, output_path: str | Path) -> Path:
        src = self.storage_dir / parse_cid_from_uri(cid)
        if not src.exists():
            raise FileNotFoundError(
                f"CID {cid!r} not found in mock IPFS store ({self.storage_dir})"
            )
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        return out


class PinataIPFSClient(BaseIPFSClient):
    """
    Upload/download via the Pinata pinning service.

    Requires a PINATA_JWT. Network access is only attempted lazily inside
    the methods, so importing this class never forces a network dependency.
    """

    provider = "pinata"

    def __init__(self, jwt: str | None = None, api_url: str | None = None):
        self.jwt = jwt if jwt is not None else PINATA_JWT
        self.api_url = (api_url or PINATA_API_URL).rstrip("/")

    def _require_jwt(self):
        if not self.jwt or self.jwt == "your_pinata_jwt_here":
            raise RuntimeError(
                "PINATA_JWT is not configured. Set PINATA_JWT in your .env "
                "to use the 'pinata' provider, or use IPFS_PROVIDER=mock for "
                "offline testing."
            )

    def upload_file(self, file_path: str | Path) -> IPFSUploadResult:
        self._require_jwt()
        import requests  # lazy import: only needed for the real backend

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = path.read_bytes()
        url = f"{self.api_url}/pinning/pinFileToIPFS"
        headers = {"Authorization": f"Bearer {self.jwt}"}
        with open(path, "rb") as fh:
            resp = requests.post(
                url, headers=headers, files={"file": (path.name, fh)}, timeout=120
            )
        resp.raise_for_status()
        cid = resp.json()["IpfsHash"]

        return IPFSUploadResult(
            cid=cid,
            uri=format_ipfs_uri(cid),
            gateway_url=gateway_url(cid),
            provider=self.provider,
            uploaded_at_utc=_now_utc(),
            file_sha256=_sha256_bytes(content),
        )

    def download_file(self, cid: str, output_path: str | Path) -> Path:
        import requests  # lazy import: only needed for the real backend

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(self.gateway_url(parse_cid_from_uri(cid)), timeout=120)
        resp.raise_for_status()
        out.write_bytes(resp.content)
        return out


# ══════════════════════════════════════════════════════════════════
# Factory
# ══════════════════════════════════════════════════════════════════

def get_client(provider: str | None = None) -> BaseIPFSClient:
    """
    Return an IPFS client for the requested provider.

    Args:
        provider: 'mock' / 'mock-ipfs' / 'pinata'. Defaults to IPFS_PROVIDER.

    Raises:
        ValueError: If the provider name is not recognised.
    """
    name = (provider or IPFS_PROVIDER or "mock").lower()
    if name in ("mock", "mock-ipfs", "local-mock"):
        return MockIPFSClient()
    if name == "pinata":
        return PinataIPFSClient()
    raise ValueError(
        f"Unknown IPFS provider: {name!r}. Supported: 'mock', 'pinata'."
    )


# ══════════════════════════════════════════════════════════════════
# Evidence-package metadata helpers
# ══════════════════════════════════════════════════════════════════

def build_ipfs_metadata(record) -> dict:
    """
    Build the dict written to ``ipfs/ipfs_metadata.json`` in an evidence
    package, from an EvidenceRecord that carries IPFS fields.
    """
    cid = record.ipfs_cid
    return {
        "ipfs_cid": cid,
        "ipfs_uri": record.ipfs_uri or (format_ipfs_uri(cid) if cid else ""),
        "gateway_urls": gateway_urls(cid) if cid else [],
        "provider": record.ipfs_provider,
        "uploaded_at_utc": record.ipfs_uploaded_at,
        "file_sha256": record.file_hash,
        "ipfs_sha256": record.ipfs_sha256,
    }
