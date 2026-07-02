"""
network_context.py — Network-aware Web3 connection context (Stage 12)

Creates a validated (Web3, contract_address) context for a given network
key.  Raises clear errors when env vars are missing or the RPC node's
reported chain ID does not match the configured chain ID — so a mis-wired
RPC + contract pair is caught before any transaction is sent.

Stage 13 additions:
  - create_network_context_for_deployment(): same RPC + chain-ID checks but
    no contract address requirement (deployment is what CREATES the address)
  - resolve_contract_address(): env var first, then latest deployment record
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


def resolve_contract_address(network_key: str) -> str:
    """Resolve the contract address for a network (Stage 13).

    Priority:
      1. The network's contract address env var (e.g. SEPOLIA_CONTRACT_ADDRESS)
      2. The latest deployment record stored in SQLite
      3. Raise ValueError

    Raises:
        ValueError: no address in env and no deployment record found.
    """
    cfg = load_network_config(network_key)

    env_address = cfg.contract_address
    if env_address:
        return env_address

    from proof_client.deployment_repository import get_latest_deployment

    latest = get_latest_deployment(cfg.network_key)
    if latest and latest.contract_address:
        return latest.contract_address

    raise ValueError(
        f"Missing contract address for network {cfg.network_key!r}. "
        f"Set env var {cfg.contract_address_env_key} or deploy the contract "
        f"first: python -m proof_client.deploy_contract --network {cfg.network_key}"
    )


def _connect_validated(config: NetworkConfig) -> Web3:
    """Connect to the network RPC and validate the reported chain ID."""
    if not config.rpc_url:
        raise ValueError(
            f"Missing RPC URL for network {config.network_key!r}. "
            f"Set env var: {config.rpc_url_env_key}"
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
    return web3


def create_network_context(network_key: str | None = None) -> NetworkContext:
    """Build a NetworkContext for *network_key* (defaults to DEFAULT_NETWORK).

    Raises:
        ValueError: missing RPC URL env var, unresolvable contract address,
                    or chain ID reported by the node does not match config.
        ConnectionError: RPC node is unreachable.
    """
    if network_key is None:
        network_key = get_default_network_key()

    config = load_network_config(network_key)

    # Stage 13: env var first, then deployment records, then a clear error.
    contract_address = resolve_contract_address(config.network_key)

    web3 = _connect_validated(config)

    return NetworkContext(
        config=config,
        web3=web3,
        contract_address=contract_address,
    )


def create_network_context_for_deployment(
    network_key: str | None = None,
) -> NetworkContext:
    """Build a NetworkContext for DEPLOYING a contract (Stage 13).

    Identical RPC + chain-ID validation as create_network_context, but no
    contract address is required — deployment is the step that creates it.
    """
    if network_key is None:
        network_key = get_default_network_key()

    config = load_network_config(network_key)
    web3 = _connect_validated(config)

    return NetworkContext(
        config=config,
        web3=web3,
        contract_address="",
    )
