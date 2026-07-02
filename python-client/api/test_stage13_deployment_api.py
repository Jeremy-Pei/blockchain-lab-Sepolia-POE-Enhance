"""
test_stage13_deployment_api.py — Stage 13 API test suite (deployment endpoints)

Tests:
  1. GET /deployments (list, filter)
  2. GET /deployments/latest
  3. POST /deployments/deploy (confirm guard, dry run, success, errors)
  4. /networks deployment status fields
  5. Private key never exposed by the API
  6. OpenAPI paths

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m api.test_stage13_deployment_api
"""

import os
import sys
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

warnings.filterwarnings("ignore")

# ── Test-isolation setup ──────────────────────────────────────────

import proof_client.deployment_repository as dep_repo

_TMP = Path(tempfile.mkdtemp(prefix="stage13_dep_api_"))
dep_repo.DB_PATH = _TMP / "deployments.db"

from fastapi.testclient import TestClient  # noqa: E402
from api.main import app  # noqa: E402

client = TestClient(app)

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


def _fake_record(network_key="anvil", address="0xDEPLOYED"):
    from proof_client.deployment_record import DeploymentRecord
    return DeploymentRecord(
        network_key=network_key,
        network_display_name="Anvil Local",
        chain_id=31337,
        contract_address=address,
        deployer_address="0xDEADBEEF",
        transaction_hash="0x" + "ab" * 32,
        block_number=42,
        gas_used=480_000,
        effective_gas_price_wei=10**9,
        deployment_fee_wei=480_000 * 10**9,
        deployment_fee_eth="0.00048",
    )


# ══════════════════════════════════════════════════════════════════
# 1. GET /deployments
# ══════════════════════════════════════════════════════════════════


def test_list_deployments():
    section("GET /deployments")

    r = client.get("/deployments")
    check("T01 GET /deployments → 200", r.status_code == 200, str(r.status_code))
    j = r.json()
    check("T02 status ok", j.get("status") == "ok")
    check("T03 empty list initially", j.get("count") == 0)

    dep_repo.save_deployment_record(_fake_record("anvil", "0xA1"))
    dep_repo.save_deployment_record(_fake_record("sepolia", "0xS1"))
    dep_repo.save_deployment_record(_fake_record("anvil", "0xA2"))

    r2 = client.get("/deployments")
    j2 = r2.json()
    check("T04 lists all records", j2["count"] == 3)
    check("T05 newest first",
          j2["deployments"][0]["contract_address"] == "0xA2")

    r3 = client.get("/deployments", params={"network": "anvil"})
    check("T06 filters by network", r3.json()["count"] == 2)

    r4 = client.get("/deployments", params={"network": "base-sepolia"})
    check("T07 hyphenated key normalised (empty ok)", r4.json()["count"] == 0)

    dep = j2["deployments"][0]
    check("T08 record has fee fields",
          dep["deployment_fee_eth"] == "0.00048" and dep["gas_used"] == 480_000)


# ══════════════════════════════════════════════════════════════════
# 2. GET /deployments/latest
# ══════════════════════════════════════════════════════════════════


def test_latest_deployment():
    section("GET /deployments/latest")

    r = client.get("/deployments/latest", params={"network": "anvil"})
    check("T09 latest → 200", r.status_code == 200, str(r.status_code))
    j = r.json()
    check("T10 returns latest anvil deployment",
          j["deployment"]["contract_address"] == "0xA2")

    r2 = client.get("/deployments/latest", params={"network": "base_sepolia"})
    check("T11 no record → 404", r2.status_code == 404)
    check("T12 404 error envelope", r2.json().get("status") == "error")

    r3 = client.get("/deployments/latest", params={"network": "unknown_xyz"})
    check("T13 unknown network → 404", r3.status_code == 404)

    r4 = client.get("/deployments/latest",
                    params={"network": "anvil", "contract_name": "Other"})
    check("T14 contract_name respected", r4.status_code == 404)


# ══════════════════════════════════════════════════════════════════
# 3. POST /deployments/deploy
# ══════════════════════════════════════════════════════════════════


def test_deploy_endpoint():
    section("POST /deployments/deploy")

    # confirm guard
    r = client.post("/deployments/deploy", json={"network": "anvil"})
    check("T15 no confirm → 400", r.status_code == 400, str(r.status_code))
    j = r.json()
    check("T16 error envelope", j.get("status") == "error")
    check("T17 message explains confirm requirement",
          "confirm=true" in j.get("message", ""))

    r2 = client.post("/deployments/deploy",
                     json={"network": "anvil", "confirm": False})
    check("T18 confirm=false → 400", r2.status_code == 400)

    # unknown network
    r3 = client.post("/deployments/deploy",
                     json={"network": "unknown_xyz", "confirm": True})
    check("T19 unknown network → 404", r3.status_code == 404)

    # dry run does not require confirm
    with patch("proof_client.deploy_contract.deploy_contract",
               return_value=None) as mock_deploy:
        r4 = client.post("/deployments/deploy",
                         json={"network": "anvil", "dry_run": True})
        check("T20 dry run without confirm → 200", r4.status_code == 200,
              str(r4.status_code))
        j4 = r4.json()
        check("T21 dry run flagged", j4.get("dry_run") is True)
        check("T22 dry run passed dry_run=True to deployer",
              mock_deploy.call_args.kwargs.get("dry_run") is True)

    # successful deployment
    record = _fake_record("anvil", "0xFRESH")
    with patch("proof_client.deploy_contract.deploy_contract",
               return_value=record) as mock_deploy:
        r5 = client.post("/deployments/deploy",
                         json={"network": "anvil", "confirm": True})
        check("T23 confirmed deploy → 200", r5.status_code == 200,
              str(r5.status_code))
        j5 = r5.json()
        check("T24 deployment returned",
              j5["deployment"]["contract_address"] == "0xFRESH")
        check("T25 update_env not called by default",
              mock_deploy.call_args.kwargs.get("allow_mainnet") is False)

    # update_env flag
    with patch("proof_client.deploy_contract.deploy_contract",
               return_value=record), \
         patch("proof_client.deploy_contract.update_env_contract_address") as mock_env:
        r6 = client.post("/deployments/deploy",
                         json={"network": "anvil", "confirm": True,
                               "update_env": True})
        check("T26 update_env deploy → 200", r6.status_code == 200)
        check("T27 .env updater invoked with network env key",
              mock_env.call_args.args[0] == "ANVIL_CONTRACT_ADDRESS"
              and mock_env.call_args.args[1] == "0xFRESH")

    # deployment errors surface as 400 with the error envelope
    with patch("proof_client.deploy_contract.deploy_contract",
               side_effect=ValueError("Mainnet deployment is disabled by default.")):
        r7 = client.post("/deployments/deploy",
                         json={"network": "anvil", "confirm": True})
        check("T28 ValueError → 400", r7.status_code == 400)
        check("T29 mainnet guard message surfaced",
              "Mainnet deployment is disabled" in r7.json()["message"])


# ══════════════════════════════════════════════════════════════════
# 4. /networks deployment status
# ══════════════════════════════════════════════════════════════════


def test_network_status_fields():
    section("/networks Deployment Status")

    r = client.get("/networks")
    j = r.json()
    anvil = next(n for n in j["networks"] if n["network_key"] == "anvil")
    check("T30 network has configured flag", anvil.get("configured") is True)
    check("T31 network has deployed flag", anvil.get("deployed") is True)
    check("T32 network has ready flag", anvil.get("ready") is True)
    check("T33 contract_address resolved from deployments",
          anvil.get("contract_address") == "0xA2")

    base = next(n for n in j["networks"] if n["network_key"] == "base_sepolia")
    original = os.environ.pop("BASE_SEPOLIA_CONTRACT_ADDRESS", None)
    try:
        r2 = client.get("/networks/base_sepolia")
        j2 = r2.json()
        check("T34 undeployed network: deployed false", j2["deployed"] is False)
        check("T35 undeployed network: ready false", j2["ready"] is False)

        os.environ["BASE_SEPOLIA_CONTRACT_ADDRESS"] = "0xENVSET"
        r3 = client.get("/networks/base_sepolia")
        j3 = r3.json()
        check("T36 env address makes network ready", j3["ready"] is True)
        check("T37 env address wins", j3["contract_address"] == "0xENVSET")
        check("T38 deployed still false with env-only address",
              j3["deployed"] is False)
    finally:
        if original is not None:
            os.environ["BASE_SEPOLIA_CONTRACT_ADDRESS"] = original
        else:
            os.environ.pop("BASE_SEPOLIA_CONTRACT_ADDRESS", None)


# ══════════════════════════════════════════════════════════════════
# 5. Private key never exposed
# ══════════════════════════════════════════════════════════════════


def test_private_key_never_exposed():
    section("Private Key Safety")

    fake_key = "0x" + "77" * 32
    original = os.environ.get("PRIVATE_KEY")
    try:
        os.environ["PRIVATE_KEY"] = fake_key

        for path in ("/deployments", "/deployments/latest?network=anvil",
                     "/networks", "/networks/anvil"):
            r = client.get(path)
            check(f"T{39 + ['/deployments', '/deployments/latest?network=anvil', '/networks', '/networks/anvil'].index(path)} "
                  f"{path} never contains private key",
                  fake_key not in r.text and "77" * 16 not in r.text)

        record = _fake_record("anvil", "0xSAFE")
        with patch("proof_client.deploy_contract.deploy_contract",
                   return_value=record):
            r = client.post("/deployments/deploy",
                            json={"network": "anvil", "confirm": True})
            check("T43 deploy response never contains private key",
                  fake_key not in r.text)
    finally:
        if original is not None:
            os.environ["PRIVATE_KEY"] = original
        else:
            os.environ.pop("PRIVATE_KEY", None)


# ══════════════════════════════════════════════════════════════════
# 6. OpenAPI
# ══════════════════════════════════════════════════════════════════


def test_openapi():
    section("OpenAPI Paths")

    paths = client.get("/openapi.json").json()["paths"]
    check("T44 /deployments documented", "/deployments" in paths)
    check("T45 /deployments/latest documented", "/deployments/latest" in paths)
    check("T46 /deployments/deploy documented", "/deployments/deploy" in paths)


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print("  Stage 13 API Tests — Deployment Endpoints")
    print("=" * 60)

    test_list_deployments()
    test_latest_deployment()
    test_deploy_endpoint()
    test_network_status_fields()
    test_private_key_never_exposed()
    test_openapi()

    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  Stage 13 Deployment API Results: {_passed}/{total} passed, {_failed} failed")
    print(f"{'=' * 60}\n")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
