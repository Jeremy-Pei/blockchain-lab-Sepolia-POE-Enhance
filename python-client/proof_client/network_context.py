"""
network_context.py — Network-aware Web3 connection context (Stage 12)

Creates a validated (Web3, contract_address) context for a given network
key.  Raises clear errors when env vars are missing or the RPC node's
reported chain ID does not match the configured chain ID — so a mis-wired
RPC + contract pair is caught before any transaction is sent.
"""

from dataclasses import dataclass

from web3 import Web3

from proof_client.network_config import (
    NetworkConfig,
    get_default_network_key,
    load_network_config,
)


@dataclass
class NetworkContext:
    config: NetworkConfig
    web3: Web3
    contract_address: str


def create_network_context(network_key: str | None = None) -> NetworkContext:
    """Build a NetworkContext for *network_key* (defaults to DEFAULT_NETWORK).

    Raises:
        ValueError: missing RPC URL env var, missing contract address env var,
                    or chain ID reported by the node does not match config.
        ConnectionError: RPC node is unreachable.
    """
    if network_key is None:
        network_key = get_default_network_key()

    config = load_network_config(network_key)

    if not config.rpc_url:
        raise ValueError(
            f"Missing RPC URL for network {config.network_key!r}. "
            f"Set env var: {config.rpc_url_env_key}"
        )
    if not config.contract_address:
        raise ValueError(
            f"Missing contract address for network {config.network_key!r}. "
            f"Set env var: {config.contract_address_env_key}"
        )

    web3 = Web3(Web3.HTTPProvider(config.rpc_url))
    if not web3.is_connected():
        raise ConnectionError(
            f"Cannot connect to {config.network_key!r} RPC: {config.rpc_url}"
        )

    actual_chain_id = web3.eth.chain_id
    if actual_chain_id != config.chain_id:
        raise ValueError(
            f"Chain ID mismatch for {config.network_key!r}: "
            f"expected {config.chain_id}, got {actual_chain_id}. "
            f"Check {config.rpc_url_env_key}."
        )

    return NetworkContext(
        config=config,
        web3=web3,
        contract_address=config.contract_address,
    )
