"""
test_stage13_deployment.py — Stage 13 test suite (deployment automation)

Tests:
  1. DeploymentRecord schema + serialisation
  2. Deployment repository (save / list / latest)
  3. Contract address resolution (env → deployment records → error)
  4. Deployment network context (no contract address required)
  5. Foundry artifact loading
  6. Safety guards (mainnet, private key, confirm)
  7. .env update helper
  8. Deploy CLI argument parsing
  9. Full mocked deployment flow

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m proof_client.test_stage13_deployment
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# ══════════════════════════════════════════════════════════════════
# Test helpers
# ══════════════════════════════════════════════════════════════════

_passed = 0
_failed = 0


def ok(name: str, detail: str = ""):
    global _passed
    _passed += 1
    suffix = f" → {detail}" if detail else ""
    print(f"  ✅ {name}{suffix}")


def fail(name: str, err: str):
    global _failed
    _failed += 1
    print(f"  ❌ {name} → {err}")


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        ok(name, detail)
    else:
        fail(name, detail or "assertion failed")


def section(title: str):
    print(f"\n{'━'*60}")
    print(f"  🚀 {title}")
    print(f"{'━'*60}")


# Well-known Anvil dev key (account #0) — safe to hard-code in tests.
_TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
_TEST_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="stage13_dep_"))


# ══════════════════════════════════════════════════════════════════
# 1. DeploymentRecord schema
# ══════════════════════════════════════════════════════════════════


def test_deployment_record():
    section("DeploymentRecord Schema")
    from proof_client.deployment_record import DeploymentRecord, utc_now_iso

    r = DeploymentRecord()
    check("T01 default record_type", r.record_type == "contract_deployment")
    check("T02 default contract_name", r.contract_name == "ProofOfExistence")
    check("T03 created_at_utc auto-filled", bool(r.created_at_utc))

    r2 = DeploymentRecord(
        network_key="base_sepolia",
        network_display_name="Base Sepolia",
        chain_id=84532,
        contract_address="0xABC",
        deployer_address=_TEST_ADDR,
        transaction_hash="0x" + "aa" * 32,
        block_number=123,
        gas_used=500_000,
        effective_gas_price_wei=1_000_000_000,
        deployment_fee_wei=500_000 * 1_000_000_000,
        deployment_fee_eth="0.0005",
    )
    check("T04 network_key stored", r2.network_key == "base_sepolia")
    check("T05 chain_id stored", r2.chain_id == 84532)
    check("T06 fee fields stored", r2.deployment_fee_eth == "0.0005")

    d = r2.to_dict()
    check("T07 to_dict has contract_address", d["contract_address"] == "0xABC")
    check("T08 to_dict has gas_used", d["gas_used"] == 500_000)

    r3 = DeploymentRecord.from_dict({**d, "unknown_key": "ignored", "id": 7})
    check("T09 from_dict filters unknown keys", r3.contract_address == "0xABC")
    check("T10 from_dict round-trip", r3.to_dict() == d)

    check("T11 utc_now_iso is ISO format", "T" in utc_now_iso())


# ══════════════════════════════════════════════════════════════════
# 2. Deployment repository
# ══════════════════════════════════════════════════════════════════


def test_deployment_repository():
    section("Deployment Repository")
    from proof_client.deployment_record import DeploymentRecord
    from proof_client.deployment_repository import (
        get_latest_deployment,
        init_deployment_db,
        list_deployment_records,
        save_deployment_record,
    )

    db = _tmp() / "dep.db"
    init_deployment_db(db_path=db)
    check("T12 init creates db file", db.exists())

    check("T13 empty list", list_deployment_records(db_path=db) == [])
    check("T14 empty latest is None",
          get_latest_deployment("anvil", db_path=db) is None)

    r1 = DeploymentRecord(network_key="anvil", chain_id=31337,
                          contract_address="0xAAA")
    rid = save_deployment_record(r1, db_path=db)
    check("T15 save returns row id", rid == 1)

    r2 = DeploymentRecord(network_key="anvil", chain_id=31337,
                          contract_address="0xBBB")
    save_deployment_record(r2, db_path=db)
    r3 = DeploymentRecord(network_key="sepolia", chain_id=11155111,
                          contract_address="0xCCC")
    save_deployment_record(r3, db_path=db)

    all_records = list_deployment_records(db_path=db)
    check("T16 list returns all", len(all_records) == 3)
    check("T17 list is newest-first", all_records[0].contract_address == "0xCCC")

    anvil_records = list_deployment_records("anvil", db_path=db)
    check("T18 list filters by network", len(anvil_records) == 2)

    latest = get_latest_deployment("anvil", db_path=db)
    check("T19 latest returns newest deployment",
          latest.contract_address == "0xBBB")

    check("T20 latest respects contract_name",
          get_latest_deployment("anvil", contract_name="Other", db_path=db) is None)

    latest_sep = get_latest_deployment("sepolia", db_path=db)
    check("T21 latest per-network isolation", latest_sep.contract_address == "0xCCC")


# ══════════════════════════════════════════════════════════════════
# 3. Contract address resolution
# ══════════════════════════════════════════════════════════════════


def test_contract_address_resolution():
    section("Contract Address Resolution")
    from proof_client.deployment_record import DeploymentRecord
    from proof_client.network_context import resolve_contract_address

    original = os.environ.get("ANVIL_CONTRACT_ADDRESS")
    try:
        # 1) env var wins
        os.environ["ANVIL_CONTRACT_ADDRESS"] = "0xENV"
        check("T22 env var has priority",
              resolve_contract_address("anvil") == "0xENV")

        # 2) falls back to deployment records
        del os.environ["ANVIL_CONTRACT_ADDRESS"]
        fake = DeploymentRecord(network_key="anvil", chain_id=31337,
                                contract_address="0xDEPLOYED")
        with patch("proof_client.deployment_repository.get_latest_deployment",
                   return_value=fake):
            check("T23 falls back to deployment record",
                  resolve_contract_address("anvil") == "0xDEPLOYED")

        # 3) env var beats deployment record
        os.environ["ANVIL_CONTRACT_ADDRESS"] = "0xENV2"
        with patch("proof_client.deployment_repository.get_latest_deployment",
                   return_value=fake):
            check("T24 env var beats deployment record",
                  resolve_contract_address("anvil") == "0xENV2")

        # 4) clear error when neither exists
        del os.environ["ANVIL_CONTRACT_ADDRESS"]
        with patch("proof_client.deployment_repository.get_latest_deployment",
                   return_value=None):
            try:
                resolve_contract_address("anvil")
                fail("T25 missing address raises ValueError", "did not raise")
            except ValueError as e:
                ok("T25 missing address raises ValueError")
                check("T26 error names the env var",
                      "ANVIL_CONTRACT_ADDRESS" in str(e))
                check("T27 error suggests deploy command",
                      "deploy_contract" in str(e))

        # 5) hyphenated key normalised
        os.environ["ANVIL_CONTRACT_ADDRESS"] = "0xENV3"
        check("T28 network key normalisation",
              resolve_contract_address("ANVIL") == "0xENV3")
    finally:
        if original is not None:
            os.environ["ANVIL_CONTRACT_ADDRESS"] = original
        elif "ANVIL_CONTRACT_ADDRESS" in os.environ:
            del os.environ["ANVIL_CONTRACT_ADDRESS"]


# ══════════════════════════════════════════════════════════════════
# 4. Deployment network context
# ══════════════════════════════════════════════════════════════════


def _fake_web3(chain_id: int):
    w3 = MagicMock()
    w3.is_connected.return_value = True
    w3.eth.chain_id = chain_id
    return w3


def test_deployment_context():
    section("Deployment Network Context")
    import proof_client.network_context as ctx_mod

    original = os.environ.get("ANVIL_RPC_URL")
    original_addr = os.environ.get("ANVIL_CONTRACT_ADDRESS")
    try:
        os.environ["ANVIL_RPC_URL"] = "http://127.0.0.1:8545"
        os.environ.pop("ANVIL_CONTRACT_ADDRESS", None)

        # Deployment context must NOT require a contract address.
        with patch.object(ctx_mod, "Web3") as mock_w3_cls:
            mock_w3_cls.HTTPProvider = MagicMock()
            mock_w3_cls.return_value = _fake_web3(31337)
            ctx = ctx_mod.create_network_context_for_deployment("anvil")
            check("T29 deployment context without contract address",
                  ctx.contract_address == "")
            check("T30 deployment context has config",
                  ctx.config.network_key == "anvil")

        # Normal context WOULD fail without an address (and no deployments).
        with patch("proof_client.deployment_repository.get_latest_deployment",
                   return_value=None):
            with patch.object(ctx_mod, "Web3") as mock_w3_cls:
                mock_w3_cls.HTTPProvider = MagicMock()
                mock_w3_cls.return_value = _fake_web3(31337)
                try:
                    ctx_mod.create_network_context("anvil")
                    fail("T31 normal context requires address", "did not raise")
                except ValueError:
                    ok("T31 normal context requires address")

        # Normal context resolves the address from deployment records.
        from proof_client.deployment_record import DeploymentRecord
        fake = DeploymentRecord(network_key="anvil", chain_id=31337,
                                contract_address="0xFROMDB")
        with patch("proof_client.deployment_repository.get_latest_deployment",
                   return_value=fake):
            with patch.object(ctx_mod, "Web3") as mock_w3_cls:
                mock_w3_cls.HTTPProvider = MagicMock()
                mock_w3_cls.return_value = _fake_web3(31337)
                ctx = ctx_mod.create_network_context("anvil")
                check("T32 normal context resolves from deployment records",
                      ctx.contract_address == "0xFROMDB")

        # Chain-ID mismatch still raises in the deployment context.
        with patch.object(ctx_mod, "Web3") as mock_w3_cls:
            mock_w3_cls.HTTPProvider = MagicMock()
            mock_w3_cls.return_value = _fake_web3(1)
            try:
                ctx_mod.create_network_context_for_deployment("anvil")
                fail("T33 chain-ID mismatch raises", "did not raise")
            except ValueError as e:
                ok("T33 chain-ID mismatch raises", "expected 31337")
                check("T34 mismatch error mentions both ids",
                      "31337" in str(e) and "1" in str(e))

        # Missing RPC URL raises.
        del os.environ["ANVIL_RPC_URL"]
        try:
            ctx_mod.create_network_context_for_deployment("anvil")
            fail("T35 missing RPC URL raises", "did not raise")
        except ValueError as e:
            ok("T35 missing RPC URL raises")
            check("T36 error names the RPC env var", "ANVIL_RPC_URL" in str(e))
    finally:
        if original is not None:
            os.environ["ANVIL_RPC_URL"] = original
        elif "ANVIL_RPC_URL" in os.environ:
            del os.environ["ANVIL_RPC_URL"]
        if original_addr is not None:
            os.environ["ANVIL_CONTRACT_ADDRESS"] = original_addr


# ══════════════════════════════════════════════════════════════════
# 5. Foundry artifact loading
# ══════════════════════════════════════════════════════════════════


def test_artifact_loading():
    section("Foundry Artifact Loading")
    from proof_client.deploy_contract import (
        DEFAULT_ARTIFACT_PATH,
        load_foundry_artifact,
        resolve_artifact_path,
    )

    tmp = _tmp()

    # Missing artifact → clear error
    try:
        load_foundry_artifact(tmp / "missing.json")
        fail("T37 missing artifact raises", "did not raise")
    except FileNotFoundError as e:
        ok("T37 missing artifact raises")
        check("T38 error suggests forge build", "forge build" in str(e))

    # Missing abi
    bad1 = tmp / "no_abi.json"
    bad1.write_text(json.dumps({"bytecode": {"object": "0x60"}}))
    try:
        load_foundry_artifact(bad1)
        fail("T39 artifact without abi raises", "did not raise")
    except ValueError:
        ok("T39 artifact without abi raises")

    # Missing bytecode.object
    bad2 = tmp / "no_bytecode.json"
    bad2.write_text(json.dumps({"abi": [], "bytecode": {}}))
    try:
        load_foundry_artifact(bad2)
        fail("T40 artifact without bytecode raises", "did not raise")
    except ValueError:
        ok("T40 artifact without bytecode raises")

    # Valid artifact
    good = tmp / "good.json"
    good.write_text(json.dumps({"abi": [{"type": "constructor"}],
                                "bytecode": {"object": "0x6080"}}))
    art = load_foundry_artifact(good)
    check("T41 valid artifact loads", art["bytecode"]["object"] == "0x6080")

    # The real Foundry artifact (if forge build has run) also loads
    if DEFAULT_ARTIFACT_PATH.exists():
        real = load_foundry_artifact(DEFAULT_ARTIFACT_PATH)
        check("T42 real ProofOfExistence artifact loads",
              isinstance(real["abi"], list) and len(real["abi"]) > 0)
        check("T43 real artifact bytecode is hex",
              real["bytecode"]["object"].startswith("0x"))
    else:
        ok("T42 real artifact not built — skipped")
        ok("T43 real artifact not built — skipped")

    # Path resolution priority
    check("T44 explicit path wins",
          resolve_artifact_path(str(good)) == good.resolve())
    original = os.environ.get("FOUNDRY_ARTIFACT_PATH")
    try:
        os.environ["FOUNDRY_ARTIFACT_PATH"] = str(good)
        check("T45 env var used when no explicit path",
              resolve_artifact_path(None) == good)
        del os.environ["FOUNDRY_ARTIFACT_PATH"]
        check("T46 default path when nothing set",
              resolve_artifact_path(None) == DEFAULT_ARTIFACT_PATH)
    finally:
        if original is not None:
            os.environ["FOUNDRY_ARTIFACT_PATH"] = original


# ══════════════════════════════════════════════════════════════════
# 6. Safety guards
# ══════════════════════════════════════════════════════════════════


def test_safety_guards():
    section("Safety Guards")
    from proof_client.deploy_contract import check_mainnet_guard, get_private_key
    from proof_client.network_config import load_network_config

    # Mainnet guard
    cfg = load_network_config("sepolia")
    try:
        check_mainnet_guard(cfg)
        ok("T47 testnet passes mainnet guard")
    except ValueError as e:
        fail("T47 testnet passes mainnet guard", str(e))

    import dataclasses
    mainnet_cfg = dataclasses.replace(cfg, is_testnet=False)
    try:
        check_mainnet_guard(mainnet_cfg)
        fail("T48 mainnet blocked by default", "did not raise")
    except ValueError as e:
        ok("T48 mainnet blocked by default")
        check("T49 mainnet error mentions --allow-mainnet",
              "--allow-mainnet" in str(e))

    try:
        check_mainnet_guard(mainnet_cfg, allow_mainnet=True)
        ok("T50 --allow-mainnet overrides guard")
    except ValueError as e:
        fail("T50 --allow-mainnet overrides guard", str(e))

    # Private key
    original = os.environ.get("PRIVATE_KEY")
    try:
        os.environ["PRIVATE_KEY"] = _TEST_KEY
        check("T51 private key read from env", get_private_key() == _TEST_KEY)

        del os.environ["PRIVATE_KEY"]
        try:
            get_private_key()
            fail("T52 missing private key raises", "did not raise")
        except ValueError as e:
            ok("T52 missing private key raises")
            check("T53 error never echoes key material",
                  _TEST_KEY not in str(e) and _TEST_KEY[2:10] not in str(e))
    finally:
        if original is not None:
            os.environ["PRIVATE_KEY"] = original


# ══════════════════════════════════════════════════════════════════
# 7. .env update helper
# ══════════════════════════════════════════════════════════════════


def test_env_update():
    section(".env Update Helper")
    from proof_client.deploy_contract import update_env_contract_address

    tmp = _tmp()
    env = tmp / ".env"
    env.write_text(
        "PRIVATE_KEY=secret\n"
        "ANVIL_CONTRACT_ADDRESS=0xOLD\n"
        "SEPOLIA_RPC_URL=https://rpc\n"
    )

    update_env_contract_address("ANVIL_CONTRACT_ADDRESS", "0xNEW", env_path=env)
    text = env.read_text()
    check("T54 existing entry replaced", "ANVIL_CONTRACT_ADDRESS=0xNEW" in text)
    check("T55 old value removed", "0xOLD" not in text)
    check("T56 other lines preserved",
          "PRIVATE_KEY=secret" in text and "SEPOLIA_RPC_URL=https://rpc" in text)
    check("T57 process env updated",
          os.environ.get("ANVIL_CONTRACT_ADDRESS") == "0xNEW")
    os.environ.pop("ANVIL_CONTRACT_ADDRESS", None)

    update_env_contract_address("BASE_SEPOLIA_CONTRACT_ADDRESS", "0xADDED",
                                env_path=env)
    check("T58 missing entry appended",
          "BASE_SEPOLIA_CONTRACT_ADDRESS=0xADDED" in env.read_text())
    os.environ.pop("BASE_SEPOLIA_CONTRACT_ADDRESS", None)

    env2 = tmp / "new.env"
    update_env_contract_address("X_CONTRACT_ADDRESS", "0xY", env_path=env2)
    check("T59 creates env file when absent",
          env2.exists() and "X_CONTRACT_ADDRESS=0xY" in env2.read_text())
    os.environ.pop("X_CONTRACT_ADDRESS", None)


# ══════════════════════════════════════════════════════════════════
# 8. CLI argument parsing
# ══════════════════════════════════════════════════════════════════


def test_cli_args():
    section("Deploy CLI Arguments")
    from proof_client.deploy_contract import _parse_args, main

    args = _parse_args(["--network", "base-sepolia", "--confirm"])
    check("T60 --network parsed", args.network == "base-sepolia")
    check("T61 --confirm parsed", args.confirm is True)
    check("T62 defaults: no dry-run", args.dry_run is False)
    check("T63 defaults: no update-env", args.update_env is False)
    check("T64 defaults: mainnet disabled", args.allow_mainnet is False)
    check("T65 default contract name",
          args.contract_name == "ProofOfExistence")

    args2 = _parse_args(["--network", "anvil", "--dry-run", "--artifact",
                         "/tmp/a.json", "--update-env", "--allow-mainnet"])
    check("T66 all flags parsed",
          args2.dry_run and args2.update_env and args2.allow_mainnet
          and args2.artifact == "/tmp/a.json")

    # Broadcast without --confirm is refused (exit code 2)
    rc = main(["--network", "anvil"])
    check("T67 broadcast without --confirm refused", rc == 2)


# ══════════════════════════════════════════════════════════════════
# 9. Full mocked deployment flow
# ══════════════════════════════════════════════════════════════════


def _mock_deploy_ctx():
    """Fake NetworkContext with a fully mocked Web3 for anvil."""
    from proof_client.network_config import load_network_config
    from proof_client.network_context import NetworkContext

    cfg = load_network_config("anvil")
    w3 = MagicMock()
    w3.eth.get_balance.return_value = 10**18
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.gas_price = 1_000_000_000
    w3.eth.estimate_gas.return_value = 500_000
    w3.eth.send_raw_transaction.return_value = bytes.fromhex("ab" * 32)

    receipt = MagicMock()
    receipt.status = 1
    receipt.contractAddress = "0xNEWCONTRACT"
    receipt.gasUsed = 480_000
    receipt.effectiveGasPrice = 1_000_000_000
    receipt.blockNumber = 42
    receipt.transactionHash.hex.return_value = "ab" * 32
    w3.eth.wait_for_transaction_receipt.return_value = receipt

    block = MagicMock()
    block.timestamp = 1_760_000_000
    w3.eth.get_block.return_value = block

    contract = MagicMock()
    contract.constructor.return_value.build_transaction.return_value = {
        "from": _TEST_ADDR, "nonce": 0, "chainId": 31337,
        "gasPrice": 1_000_000_000,
    }
    w3.eth.contract.return_value = contract

    return NetworkContext(config=cfg, web3=w3, contract_address="")


def test_mocked_deployment():
    section("Full Mocked Deployment Flow")
    import proof_client.deploy_contract as dep_mod
    import proof_client.deployment_repository as repo_mod

    tmp = _tmp()
    artifact = tmp / "artifact.json"
    artifact.write_text(json.dumps({"abi": [], "bytecode": {"object": "0x6080"}}))

    saved = []
    original_key = os.environ.get("PRIVATE_KEY")
    try:
        os.environ["PRIVATE_KEY"] = _TEST_KEY
        ctx = _mock_deploy_ctx()
        with patch.object(dep_mod, "create_network_context_for_deployment",
                          return_value=ctx), \
             patch.object(dep_mod, "save_deployment_record",
                          side_effect=lambda r: saved.append(r) or 1):
            record = dep_mod.deploy_contract("anvil", artifact_path=artifact)

        check("T68 deployment returns record", record is not None)
        check("T69 contract address from receipt",
              record.contract_address == "0xNEWCONTRACT")
        check("T70 deployer address derived from key",
              record.deployer_address == _TEST_ADDR)
        check("T71 gas_used recorded", record.gas_used == 480_000)
        check("T72 effective gas price recorded",
              record.effective_gas_price_wei == 1_000_000_000)
        check("T73 fee = gas × price",
              record.deployment_fee_wei == 480_000 * 1_000_000_000)
        check("T74 fee in ETH", record.deployment_fee_eth == "0.00048")
        check("T75 block number recorded", record.block_number == 42)
        check("T76 block timestamp recorded",
              record.block_timestamp == 1_760_000_000)
        check("T77 tx hash 0x-prefixed",
              record.transaction_hash.startswith("0x"))
        check("T78 network fields set",
              record.network_key == "anvil" and record.chain_id == 31337)
        check("T79 artifact path recorded", str(artifact) in record.artifact_path)
        check("T80 record saved to repository", len(saved) == 1)

        # Dry run: nothing broadcast, nothing saved
        saved.clear()
        ctx2 = _mock_deploy_ctx()
        with patch.object(dep_mod, "create_network_context_for_deployment",
                          return_value=ctx2), \
             patch.object(dep_mod, "save_deployment_record",
                          side_effect=lambda r: saved.append(r) or 1):
            result = dep_mod.deploy_contract("anvil", artifact_path=artifact,
                                             dry_run=True)
        check("T81 dry run returns None", result is None)
        check("T82 dry run saves nothing", len(saved) == 0)
        check("T83 dry run does not broadcast",
              ctx2.web3.eth.send_raw_transaction.call_count == 0)

        # Zero balance refused
        ctx3 = _mock_deploy_ctx()
        ctx3.web3.eth.get_balance.return_value = 0
        with patch.object(dep_mod, "create_network_context_for_deployment",
                          return_value=ctx3):
            try:
                dep_mod.deploy_contract("anvil", artifact_path=artifact)
                fail("T84 zero balance refused", "did not raise")
            except ValueError as e:
                ok("T84 zero balance refused")
                check("T85 balance error names deployer",
                      _TEST_ADDR in str(e))

        # Reverted deployment surfaces an error
        ctx4 = _mock_deploy_ctx()
        ctx4.web3.eth.wait_for_transaction_receipt.return_value.status = 0
        with patch.object(dep_mod, "create_network_context_for_deployment",
                          return_value=ctx4):
            try:
                dep_mod.deploy_contract("anvil", artifact_path=artifact)
                fail("T86 reverted deployment raises", "did not raise")
            except RuntimeError:
                ok("T86 reverted deployment raises")
    finally:
        if original_key is not None:
            os.environ["PRIVATE_KEY"] = original_key
        elif "PRIVATE_KEY" in os.environ:
            del os.environ["PRIVATE_KEY"]


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


def main_tests():
    print("=" * 60)
    print("  Stage 13 Test Suite — Deployment Automation")
    print("=" * 60)

    test_deployment_record()
    test_deployment_repository()
    test_contract_address_resolution()
    test_deployment_context()
    test_artifact_loading()
    test_safety_guards()
    test_env_update()
    test_cli_args()
    test_mocked_deployment()

    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  Stage 13 Deployment Results: {_passed}/{total} passed, {_failed} failed")
    print(f"{'=' * 60}\n")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main_tests()
