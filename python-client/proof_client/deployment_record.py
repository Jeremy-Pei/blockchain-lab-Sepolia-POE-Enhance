"""
deployment_record.py — Contract deployment record schema (Stage 13)

Defines the standardised DeploymentRecord dataclass used to persist and
serialise contract deployment metadata: which contract was deployed to
which network, by whom, in which transaction, and at what gas cost.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DeploymentRecord:
    """A single contract deployment on a specific network."""

    record_type: str = "contract_deployment"
    contract_name: str = "ProofOfExistence"
    network_key: str = ""
    network_display_name: str = ""
    chain_id: int = 0
    contract_address: str = ""
    deployer_address: str = ""
    transaction_hash: str = ""
    block_number: int = 0
    block_timestamp: int = 0
    gas_used: int = 0
    effective_gas_price_wei: int = 0
    deployment_fee_wei: int = 0
    deployment_fee_eth: str = ""
    explorer_url: str = ""
    artifact_path: str = ""
    created_at_utc: str = ""

    def __post_init__(self):
        if not self.created_at_utc:
            self.created_at_utc = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dict suitable for JSON serialisation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeploymentRecord":
        """Create a DeploymentRecord from a dict, filtering unknown keys."""
        fields = cls.__dataclass_fields__
        clean = {k: v for k, v in data.items() if k in fields}
        return cls(**clean)
