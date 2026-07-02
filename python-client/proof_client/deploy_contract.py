"""
deploy_contract.py — Deploy the ProofOfExistence contract to a network (Stage 13)

Python-first deployment: Foundry compiles (forge build), Python reads the
artifact JSON (abi + bytecode), deploys via Web3, records the deployment in
SQLite, and optionally updates the network's contract address in .env.

CLI:
  python -m proof_client.deploy_contract --network anvil --confirm
  python -m proof_client.deploy_contract --network sepolia --confirm
  python -m proof_client.deploy_contract --network base-sepolia --confirm --update-env
  python -m proof_client.deploy_contract --network anvil --dry-run

SECURITY:
  - Mainnet deployment is disabled by default (--allow-mainnet to override).
  - Broadcasting requires --confirm; --dry-run never broadcasts.
  - The private key is never printed, logged, or stored in any record.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from eth_account import Account
from web3 import Web3

from proof_client.config import PROJECT_ROOT
from proof_client.deployment_record import DeploymentRecord, utc_now_iso
from proof_client.deployment_repository import save_deployment_record
from proof_client.network_config import NetworkConfig, normalize_network_key
from proof_client.network_context import create_network_context_for_deployment


# Default Foundry artifact produced by `forge build` in contracts/.
DEFAULT_ARTIFACT_PATH = (
    PROJECT_ROOT.parent / "contracts" / "out"
    / "ProofOfExistence.sol" / "ProofOfExistence.json"
)

ENV_PATH = PROJECT_ROOT / ".env"

# Multiplier applied to the gas estimate to absorb small state differences
# between estimation and inclusion.
GAS_HEADROOM = 1.2


# ── Inputs ────────────────────────────────────────────────────────


def get_private_key() -> str:
    """Return the deployer private key from the environment.

    Raises:
        ValueError: PRIVATE_KEY is not set. The message never echoes any
                    part of the key or other .env contents.
    """
    key = os.getenv("PRIVATE_KEY", "")
    if not key:
        raise ValueError(
            "Missing PRIVATE_KEY environment variable. "
            "Set it in python-client/.env (never commit it)."
        )
    return key


def resolve_artifact_path(artifact: str | None = None) -> Path:
    """Resolve the Foundry artifact path.

    Priority: explicit --artifact > FOUNDRY_ARTIFACT_PATH env var > default.
    """
    if artifact:
        return Path(artifact).expanduser().resolve()
    env_path = os.getenv("FOUNDRY_ARTIFACT_PATH", "")
    if env_path:
        p = Path(env_path).expanduser()
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        return p
    return DEFAULT_ARTIFACT_PATH


def load_foundry_artifact(artifact_path: Path) -> dict:
    """Load a Foundry artifact JSON and validate it has abi + bytecode.

    Raises:
        FileNotFoundError: artifact does not exist (run `forge build` first).
        ValueError: artifact JSON is missing abi or bytecode.object.
    """
    if not artifact_path.exists():
        raise FileNotFoundError(
            f"Foundry artifact not found: {artifact_path}. "
            f"Run `forge build` in the contracts/ directory first."
        )
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    if "abi" not in data:
        raise ValueError(f"Artifact missing 'abi': {artifact_path}")
    bytecode = data.get("bytecode")
    if not isinstance(bytecode, dict) or not bytecode.get("object"):
        raise ValueError(f"Artifact missing 'bytecode.object': {artifact_path}")
    return data


# ── Safety guards ─────────────────────────────────────────────────


def check_mainnet_guard(config: NetworkConfig, allow_mainnet: bool = False) -> None:
    """Refuse to touch non-testnet networks unless explicitly allowed."""
    if not config.is_testnet and not allow_mainnet:
        raise ValueError(
            "Mainnet deployment is disabled by default. "
            "Pass --allow-mainnet only if you understand the risk."
        )


# ── .env update ───────────────────────────────────────────────────


def update_env_contract_address(
    env_key: str, contract_address: str, env_path: Path | None = None
) -> Path:
    """Set `env_key=contract_address` in .env, replacing any existing line.

    Only the single matching line is rewritten; the rest of the file is
    preserved byte-for-byte. Appends the entry when the key is absent.
    """
    path = env_path or ENV_PATH
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    new_line = f"{env_key}={contract_address}"
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{env_key}="):
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        lines.append(new_line)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Keep the current process consistent with the file it just wrote.
    os.environ[env_key] = contract_address
    return path


# ── Deployment flow ───────────────────────────────────────────────


def deploy_contract(
    network_key: str,
    artifact_path: Path | str | None = None,
    contract_name: str = "ProofOfExistence",
    dry_run: bool = False,
    allow_mainnet: bool = False,
) -> DeploymentRecord | None:
    """Deploy *contract_name* to *network_key* and record the deployment.

    Returns:
        DeploymentRecord on success, or None for a dry run.
    """
    artifact_file = resolve_artifact_path(
        str(artifact_path) if artifact_path else None
    )
    artifact = load_foundry_artifact(artifact_file)
    abi = artifact["abi"]
    bytecode = artifact["bytecode"]["object"]

    ctx = create_network_context_for_deployment(network_key)
    check_mainnet_guard(ctx.config, allow_mainnet=allow_mainnet)

    private_key = get_private_key()
    account = Account.from_key(private_key)

    balance_wei = ctx.web3.eth.get_balance(account.address)
    balance_eth = Web3.from_wei(balance_wei, "ether")

    print(f"🌐 Network:  {ctx.config.display_name} (chain ID {ctx.config.chain_id})")
    print(f"📦 Artifact: {artifact_file}")
    print(f"👤 Deployer: {account.address}")
    print(f"💰 Balance:  {balance_eth} {ctx.config.native_token_symbol}")

    if balance_wei == 0:
        raise ValueError(
            f"Deployer {account.address} has zero balance on "
            f"{ctx.config.display_name}. Fund it before deploying."
        )

    contract = ctx.web3.eth.contract(abi=abi, bytecode=bytecode)

    tx = contract.constructor().build_transaction({
        "from": account.address,
        "nonce": ctx.web3.eth.get_transaction_count(account.address),
        "chainId": ctx.config.chain_id,
        "gasPrice": ctx.web3.eth.gas_price,
    })

    estimated_gas = ctx.web3.eth.estimate_gas(tx)
    tx["gas"] = int(estimated_gas * GAS_HEADROOM)
    print(f"⛽ Estimated gas: {estimated_gas} (limit {tx['gas']})")

    if dry_run:
        print("\n[DRY RUN] Configuration, wallet, artifact and gas estimate OK. "
              "No transaction broadcast.")
        return None

    signed = account.sign_transaction(tx)
    tx_hash = ctx.web3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"⏳ Broadcast: 0x{tx_hash.hex().replace('0x', '')} — waiting for receipt …")
    receipt = ctx.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)

    if receipt.status != 1:
        raise RuntimeError(
            f"Deployment transaction reverted: 0x{receipt.transactionHash.hex().replace('0x', '')}"
        )

    contract_address = receipt.contractAddress
    gas_used = receipt.gasUsed
    effective_gas_price = getattr(receipt, "effectiveGasPrice", None)
    if effective_gas_price is None:
        effective_gas_price = tx.get("gasPrice", 0)
    deployment_fee_wei = gas_used * effective_gas_price
    deployment_fee_eth = str(Web3.from_wei(deployment_fee_wei, "ether"))

    try:
        block = ctx.web3.eth.get_block(receipt.blockNumber)
        block_timestamp = block.timestamp
    except Exception:
        block_timestamp = 0

    tx_hash_hex = receipt.transactionHash.hex()
    if not tx_hash_hex.startswith("0x"):
        tx_hash_hex = "0x" + tx_hash_hex
    explorer_url = ctx.config.tx_url(tx_hash_hex)

    record = DeploymentRecord(
        contract_name=contract_name,
        network_key=ctx.config.network_key,
        network_display_name=ctx.config.display_name,
        chain_id=ctx.config.chain_id,
        contract_address=contract_address,
        deployer_address=account.address,
        transaction_hash=tx_hash_hex,
        block_number=receipt.blockNumber,
        block_timestamp=block_timestamp,
        gas_used=gas_used,
        effective_gas_price_wei=effective_gas_price,
        deployment_fee_wei=deployment_fee_wei,
        deployment_fee_eth=deployment_fee_eth,
        explorer_url=explorer_url,
        artifact_path=str(artifact_file),
        created_at_utc=utc_now_iso(),
    )
    save_deployment_record(record)

    print("\n✅ Deployment successful!")
    print(f"   network_key:                 {record.network_key}")
    print(f"   chain_id:                    {record.chain_id}")
    print(f"   contract_address:            {record.contract_address}")
    print(f"   deployer_address:            {record.deployer_address}")
    print(f"   deployment_transaction_hash: {record.transaction_hash}")
    print(f"   block_number:                {record.block_number}")
    print(f"   gas_used:                    {record.gas_used}")
    print(f"   effective_gas_price:         {record.effective_gas_price_wei} wei")
    print(f"   deployment_fee_eth:          {record.deployment_fee_eth} "
          f"{ctx.config.native_token_symbol}")
    if record.explorer_url:
        print(f"   explorer_url:                {record.explorer_url}")

    return record


# ── CLI ───────────────────────────────────────────────────────────


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.deploy_contract",
        description="Deploy the ProofOfExistence contract to a configured network.",
    )
    parser.add_argument("--network", required=True,
                        help="Network key, e.g. anvil, sepolia, base-sepolia")
    parser.add_argument("--artifact", default=None,
                        help="Foundry artifact JSON path "
                        "(default: FOUNDRY_ARTIFACT_PATH env var, or "
                        "contracts/out/ProofOfExistence.sol/ProofOfExistence.json)")
    parser.add_argument("--contract-name", default="ProofOfExistence",
                        help="Contract name recorded in the deployment record")
    parser.add_argument("--confirm", action="store_true",
                        help="Required to broadcast the deployment transaction")
    parser.add_argument("--update-env", action="store_true",
                        help="After deployment, update the network's "
                        "CONTRACT_ADDRESS entry in .env")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check config, wallet, artifact and gas estimate "
                        "without broadcasting")
    parser.add_argument("--allow-mainnet", action="store_true",
                        help="Allow deployment to a non-testnet network "
                        "(disabled by default)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    network_key = normalize_network_key(args.network)

    if not args.dry_run and not args.confirm:
        print(
            "Error: deployment broadcasts an on-chain transaction and spends "
            "native tokens. Re-run with --confirm (or use --dry-run to only "
            "validate the configuration).",
            file=sys.stderr,
        )
        return 2

    try:
        record = deploy_contract(
            network_key=network_key,
            artifact_path=args.artifact,
            contract_name=args.contract_name,
            dry_run=args.dry_run,
            allow_mainnet=args.allow_mainnet,
        )
    except (ValueError, FileNotFoundError, ConnectionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if record and args.update_env:
        from proof_client.network_config import load_network_config

        cfg = load_network_config(network_key)
        env_path = update_env_contract_address(
            cfg.contract_address_env_key, record.contract_address
        )
        print(f"📝 Updated {cfg.contract_address_env_key} in {env_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
