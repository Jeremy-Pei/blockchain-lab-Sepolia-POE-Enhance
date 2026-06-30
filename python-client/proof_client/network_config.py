"""
network_config.py — Multi-network configuration layer (Stage 12)

Loads per-network JSON configs from python-client/networks/ and exposes
them as typed NetworkConfig dataclasses.  Every network config carries:
  - RPC URL (resolved from an env-var key at runtime)
  - chain_id for on-chain validation
  - contract address (resolved from an env-var key at runtime)
  - explorer URL templates for transaction and address links
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path


NETWORKS_DIR = Path(__file__).resolve().parents[1] / "networks"


@dataclass
class NetworkConfig:
    network_key: str
    display_name: str
    chain_id: int
    rpc_url_env_key: str
    explorer_base_url: str
    explorer_tx_url_template: str
    explorer_address_url_template: str
    native_token_symbol: str
    is_testnet: bool
    contract_address_env_key: str
    enabled: bool = True

    @property
    def rpc_url(self) -> str:
        return os.getenv(self.rpc_url_env_key, "")

    @property
    def contract_address(self) -> str:
        return os.getenv(self.contract_address_env_key, "")

    def tx_url(self, tx_hash: str) -> str:
        if not self.explorer_tx_url_template:
            return ""
        h = tx_hash if tx_hash.startswith("0x") else f"0x{tx_hash}"
        return self.explorer_tx_url_template.format(tx_hash=h)

    def address_url(self, address: str) -> str:
        if not self.explorer_address_url_template:
            return ""
        return self.explorer_address_url_template.format(address=address)


def normalize_network_key(network_key: str) -> str:
    """Normalise a user-supplied network key: lowercase, hyphens to underscores."""
    return network_key.replace("-", "_").strip().lower()


def load_network_config(network_key: str) -> NetworkConfig:
    """Load a NetworkConfig from the networks/ directory.

    Raises ValueError for unknown or missing network keys.
    """
    key = normalize_network_key(network_key)
    path = NETWORKS_DIR / f"{key}.json"
    if not path.exists():
        available = [p.stem for p in sorted(NETWORKS_DIR.glob("*.json"))]
        raise ValueError(
            f"Unknown network: {network_key!r}. "
            f"Available: {', '.join(available) or 'none'}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return NetworkConfig(**data)


def list_network_configs() -> list[NetworkConfig]:
    """Return all enabled NetworkConfig objects sorted by network_key."""
    configs = []
    for path in sorted(NETWORKS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        cfg = NetworkConfig(**data)
        if cfg.enabled:
            configs.append(cfg)
    return configs


def get_default_network_key() -> str:
    """Return the default network key from DEFAULT_NETWORK env var."""
    return normalize_network_key(os.getenv("DEFAULT_NETWORK", "sepolia"))


def get_default_network_config() -> NetworkConfig:
    """Return the NetworkConfig for the default network."""
    return load_network_config(get_default_network_key())
