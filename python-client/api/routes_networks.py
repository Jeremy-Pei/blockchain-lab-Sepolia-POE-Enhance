"""
routes_networks.py — Network configuration endpoints (Stage 12)

GET /networks              list all enabled network configs
GET /networks/current      return the currently active default network
GET /networks/{network_key} return a single network config by key

Stage 13: each network now also reports its deployment status —
  configured → JSON config exists (always true for listed networks)
  deployed   → a deployment record exists in SQLite
  ready      → a contract address is resolvable (env var or deployment)
"""

from fastapi import APIRouter, HTTPException

from proof_client.deployment_repository import get_latest_deployment
from proof_client.network_config import (
    NetworkConfig,
    get_default_network_key,
    list_network_configs,
    load_network_config,
)

router = APIRouter()


def _deployment_status(cfg: NetworkConfig) -> dict:
    """Stage 13: configured / deployed / ready flags + resolved address."""
    latest = get_latest_deployment(cfg.network_key)
    contract_address = cfg.contract_address or (
        latest.contract_address if latest else ""
    )
    return {
        "configured": True,
        "deployed": latest is not None,
        "ready": bool(contract_address),
        "contract_address": contract_address,
    }


@router.get("")
def list_networks():
    """List all enabled network configurations with deployment status."""
    configs = list_network_configs()
    return {
        "status": "ok",
        "count": len(configs),
        "networks": [
            {
                "network_key": c.network_key,
                "display_name": c.display_name,
                "chain_id": c.chain_id,
                "native_token_symbol": c.native_token_symbol,
                "is_testnet": c.is_testnet,
                "enabled": c.enabled,
                "explorer_base_url": c.explorer_base_url,
                **_deployment_status(c),
            }
            for c in configs
        ],
    }


@router.get("/current")
def current_network():
    """Return the currently active default network."""
    key = get_default_network_key()
    try:
        cfg = load_network_config(key)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"Default network {key!r} not found in config"
        )
    return {
        "status": "ok",
        "network_key": cfg.network_key,
        "display_name": cfg.display_name,
        "chain_id": cfg.chain_id,
        "native_token_symbol": cfg.native_token_symbol,
        "is_testnet": cfg.is_testnet,
        "explorer_base_url": cfg.explorer_base_url,
    }


@router.get("/{network_key}")
def get_network(network_key: str):
    """Return a single network configuration by key (hyphens converted to underscores)."""
    try:
        cfg = load_network_config(network_key)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown network: {network_key!r}")
    return {
        "status": "ok",
        "network_key": cfg.network_key,
        "display_name": cfg.display_name,
        "chain_id": cfg.chain_id,
        "explorer_base_url": cfg.explorer_base_url,
        "native_token_symbol": cfg.native_token_symbol,
        "is_testnet": cfg.is_testnet,
        "enabled": cfg.enabled,
        **_deployment_status(cfg),
    }
