"""
routes_deployment.py — Contract deployment endpoints (Stage 13)

GET  /deployments                  list deployment records
GET  /deployments/latest?network=  latest deployment for a network
POST /deployments/deploy           deploy the contract (requires confirm=true)

SECURITY: POST /deployments/deploy broadcasts an on-chain transaction and
spends native tokens. It therefore requires confirm=true, and non-testnet
networks are rejected unless allow_mainnet is explicitly set.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from proof_client.deployment_repository import (
    get_latest_deployment,
    list_deployment_records,
)
from proof_client.network_config import load_network_config, normalize_network_key

router = APIRouter()


class DeployRequest(BaseModel):
    network: str
    confirm: bool = False
    dry_run: bool = False
    update_env: bool = False
    allow_mainnet: bool = False
    artifact: str | None = None
    contract_name: str = "ProofOfExistence"


@router.get("")
def list_deployments(network: str | None = None):
    """List deployment records, newest first, optionally filtered by network."""
    key = normalize_network_key(network) if network else None
    records = list_deployment_records(network_key=key)
    return {
        "status": "ok",
        "count": len(records),
        "deployments": [r.to_dict() for r in records],
    }


@router.get("/latest")
def latest_deployment(network: str, contract_name: str = "ProofOfExistence"):
    """Return the latest deployment for a network."""
    key = normalize_network_key(network)
    try:
        load_network_config(key)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown network: {network!r}")

    record = get_latest_deployment(key, contract_name=contract_name)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No deployment record found for network {key!r}",
        )
    return {"status": "ok", "deployment": record.to_dict()}


@router.post("/deploy")
def deploy(req: DeployRequest):
    """Deploy the contract to a network. Requires confirm=true to broadcast."""
    if not req.dry_run and not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Deployment requires confirm=true because it broadcasts "
                   "an on-chain transaction.",
        )

    key = normalize_network_key(req.network)
    try:
        cfg = load_network_config(key)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown network: {req.network!r}")

    from proof_client.deploy_contract import (
        deploy_contract,
        update_env_contract_address,
    )

    try:
        record = deploy_contract(
            network_key=key,
            artifact_path=req.artifact,
            contract_name=req.contract_name,
            dry_run=req.dry_run,
            allow_mainnet=req.allow_mainnet,
        )
    except (ValueError, FileNotFoundError, ConnectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if record is None:
        return {
            "status": "ok",
            "dry_run": True,
            "network_key": key,
            "message": "Dry run passed: configuration, wallet, artifact and "
                       "gas estimate are valid. No transaction was broadcast.",
        }

    if req.update_env:
        update_env_contract_address(
            cfg.contract_address_env_key, record.contract_address
        )

    return {"status": "ok", "dry_run": False, "deployment": record.to_dict()}
