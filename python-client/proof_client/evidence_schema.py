"""
evidence_schema.py — Evidence data structure definition

Defines the standardised EvidenceRecord dataclass used for passing
and serialising on-chain proof data between modules.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class EvidenceRecord:
    """A single on-chain proof-of-existence record."""

    # ── File information ──
    file_name: str
    file_hash: str
    uri: str

    # ── Blockchain information ──
    tx_hash: str = ""
    block_number: int = 0
    gas_used: int = 0
    owner: str = ""
    timestamp: int = 0
    status: str = ""

    # ── Metadata ──
    network: str = "Ethereum Sepolia"
    chain_id: int = 11155111
    contract_address: str = ""
    explorer_tx_url: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ── IPFS off-chain storage (Stage 7) ──
    # Optional and defaulted, so older evidence JSON without these keys
    # still deserialises cleanly via from_dict().
    #
    # NOTE: file_hash (SHA-256) is still the PRIMARY evidence hash. The CID
    # below is only an off-chain pointer to a retrievable copy of the file.
    ipfs_cid: str = ""           # content identifier, e.g. bafy... / mock-...
    ipfs_uri: str = ""           # canonical URI, e.g. ipfs://bafy...
    ipfs_gateway_url: str = ""   # browsable HTTP gateway URL
    ipfs_provider: str = ""      # mock-ipfs / pinata / local-ipfs
    ipfs_uploaded_at: str = ""   # UTC timestamp of the IPFS upload
    ipfs_sha256: str = ""        # SHA-256 of the uploaded content (== file_hash)

    # ── Optional notes ──
    note: Optional[str] = None

    # ── Serialisation ──

    def to_dict(self) -> dict:
        """Convert to a dict suitable for JSON serialisation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceRecord":
        """Create an EvidenceRecord from a dict, filtering unknown keys."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    # ── Convenience properties ──

    @property
    def timestamp_utc(self) -> str:
        """Convert the Unix timestamp to a human-readable UTC string."""
        if self.timestamp == 0:
            return "N/A"
        return datetime.fromtimestamp(
            self.timestamp, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")

    @property
    def has_ipfs(self) -> bool:
        """True if this record carries an IPFS content identifier."""
        return bool(self.ipfs_cid)

    @property
    def explorer_link(self) -> str:
        """Full block explorer transaction link."""
        if not self.explorer_tx_url or not self.tx_hash:
            return ""
        tx = self.tx_hash if self.tx_hash.startswith("0x") else f"0x{self.tx_hash}"
        return f"{self.explorer_tx_url}{tx}"
