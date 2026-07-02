"""
test_stage13_dashboard.py — Stage 13 dashboard test suite (deploy + gas pages)

Tests:
  1. Deploy page (form, confirm checkbox, safety warning)
  2. Deploy submit (confirm guard, dry run, mocked success)
  3. Deployments history page
  4. Gas study page (form, confirm checkbox, safety warning)
  5. Gas study submit (confirm guard, dry run)
  6. Gas studies list + detail pages
  7. Navigation and home cards

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m api.test_stage13_dashboard
"""

import json
import sys
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

warnings.filterwarnings("ignore")

# ── Test-isolation setup ──────────────────────────────────────────

import api.routes_gas as gas_routes
import proof_client.deployment_repository as dep_repo

_TMP = Path(tempfile.mkdtemp(prefix="stage13_dash_"))
dep_repo.DB_PATH = _TMP / "deployments.db"
_STUDIES = _TMP / "gas_studies"
_STUDIES.mkdir()
gas_routes.GAS_STUDIES_DIR = _STUDIES

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
    print(f"  🖥 {title}")
    print(f"{'━'*60}")


# ══════════════════════════════════════════════════════════════════
# 1. Deploy page
# ══════════════════════════════════════════════════════════════════


def test_deploy_page():
    section("Deploy Page")

    r = client.get("/dashboard/deploy")
    check("T01 GET /dashboard/deploy → 200", r.status_code == 200,
          str(r.status_code))
    check("T02 network selector present", 'name="network"' in r.text)
    check("T03 confirm checkbox present", 'name="confirm"' in r.text)
    check("T04 dry-run checkbox present", 'name="dry_run"' in r.text)
    check("T05 update-env checkbox present", 'name="update_env"' in r.text)
    check("T06 safety warning shown",
          "broadcasts on-chain transactions" in r.text)
    check("T07 mainnet notice shown",
          "Mainnet deployment is disabled by default" in r.text)


# ══════════════════════════════════════════════════════════════════
# 2. Deploy submit
# ══════════════════════════════════════════════════════════════════


def test_deploy_submit():
    section("Deploy Submit")

    # No confirm → error page
    r = client.post("/dashboard/deploy", data={"network": "anvil"})
    check("T08 no confirm → 400", r.status_code == 400, str(r.status_code))
    check("T09 error explains confirm requirement", "confirm" in r.text.lower())

    # Dry run works without confirm
    with patch("proof_client.deploy_contract.deploy_contract",
               return_value=None):
        r2 = client.post("/dashboard/deploy",
                         data={"network": "anvil", "dry_run": "1"})
        check("T10 dry run without confirm → 200", r2.status_code == 200,
              str(r2.status_code))
        check("T11 dry-run message rendered", "Dry run passed" in r2.text)

    # Confirmed deployment (mocked)
    from proof_client.deployment_record import DeploymentRecord
    record = DeploymentRecord(
        network_key="anvil", network_display_name="Anvil Local",
        chain_id=31337, contract_address="0xDASHDEPLOY",
        deployer_address="0xDEAD", transaction_hash="0x" + "ab" * 32,
        gas_used=480_000, deployment_fee_eth="0.00048",
    )
    with patch("proof_client.deploy_contract.deploy_contract",
               return_value=record):
        r3 = client.post("/dashboard/deploy",
                         data={"network": "anvil", "confirm": "1"})
        check("T12 confirmed deploy → 200", r3.status_code == 200,
              str(r3.status_code))
        check("T13 result shows contract address", "0xDASHDEPLOY" in r3.text)

    # Deployment error → error page, not a crash
    with patch("proof_client.deploy_contract.deploy_contract",
               side_effect=ValueError("Missing PRIVATE_KEY environment variable.")):
        r4 = client.post("/dashboard/deploy",
                         data={"network": "anvil", "confirm": "1"})
        check("T14 error rendered as page", r4.status_code == 400)
        check("T15 error message shown", "PRIVATE_KEY" in r4.text)


# ══════════════════════════════════════════════════════════════════
# 3. Deployments page
# ══════════════════════════════════════════════════════════════════


def test_deployments_page():
    section("Deployments Page")

    r = client.get("/dashboard/deployments")
    check("T16 GET /dashboard/deployments → 200", r.status_code == 200,
          str(r.status_code))
    check("T17 empty state message", "No deployment records" in r.text)

    from proof_client.deployment_record import DeploymentRecord
    dep_repo.save_deployment_record(DeploymentRecord(
        network_key="anvil", network_display_name="Anvil Local",
        chain_id=31337, contract_address="0xHIST01",
        transaction_hash="0x" + "cd" * 32, block_number=5,
        gas_used=480_000, deployment_fee_eth="0.00048",
    ))

    r2 = client.get("/dashboard/deployments")
    check("T18 record listed", "0xHIST01" in r2.text)
    check("T19 network shown", "Anvil Local" in r2.text)
    check("T20 fee shown", "0.00048" in r2.text)


# ══════════════════════════════════════════════════════════════════
# 4. Gas study page
# ══════════════════════════════════════════════════════════════════


def test_gas_study_page():
    section("Gas Study Page")

    r = client.get("/dashboard/gas-study")
    check("T21 GET /dashboard/gas-study → 200", r.status_code == 200,
          str(r.status_code))
    check("T22 network selector present", 'name="network"' in r.text)
    check("T23 batch size input present", 'name="batch_size"' in r.text)
    check("T24 confirm checkbox present", 'name="confirm"' in r.text)
    check("T25 merkle workflow toggle present",
          'name="include_merkle"' in r.text)
    check("T26 ipfs workflow toggle present", 'name="include_ipfs"' in r.text)
    check("T27 safety warning shown",
          "broadcasts on-chain transactions" in r.text)


# ══════════════════════════════════════════════════════════════════
# 5. Gas study submit
# ══════════════════════════════════════════════════════════════════


def test_gas_study_submit():
    section("Gas Study Submit")

    r = client.post("/dashboard/gas-study",
                    data={"network": "anvil", "batch_size": "3"})
    check("T28 no confirm → 400", r.status_code == 400, str(r.status_code))
    check("T29 error explains confirm requirement", "confirm" in r.text.lower())

    fake_dry = {"study_id": "gas_study_dash_dry", "dry_run": True,
                "records": [], "workflows": ["single_file"]}
    with patch("proof_client.gas_study.run_gas_study",
               return_value=fake_dry) as mock_run:
        r2 = client.post("/dashboard/gas-study",
                         data={"network": "anvil", "batch_size": "3",
                               "dry_run": "1"})
        check("T30 dry run without confirm → 200", r2.status_code == 200,
              str(r2.status_code))
        check("T31 dry_run forwarded",
              mock_run.call_args.kwargs.get("dry_run") is True)
        check("T32 batch_size forwarded",
              mock_run.call_args.kwargs.get("batch_size") == 3)

    # Confirmed run renders the study detail page
    study = {
        "study_id": "gas_study_dash_ran", "network_key": "anvil",
        "network_display_name": "Anvil Local", "chain_id": 31337,
        "contract_address": "0xC", "native_token_symbol": "ETH",
        "batch_size": 2, "workflows": ["single_file", "merkle_batch"],
        "created_at_utc": "2026-07-02T00:00:00+00:00",
        "records": [
            {"workflow": "single_file", "file_count": 1, "gas_used": 50_000,
             "total_fee_wei": 50_000, "total_fee_eth": "5e-14",
             "transaction_hash": "0x" + "aa" * 32, "block_number": 1},
            {"workflow": "merkle_batch", "file_count": 2, "gas_used": 55_000,
             "total_fee_wei": 55_000, "total_fee_eth": "5.5e-14",
             "transaction_hash": "0x" + "bb" * 32, "block_number": 2},
        ],
        "study_dir": str(_STUDIES / "gas_study_dash_ran"),
    }
    d = _STUDIES / "gas_study_dash_ran"
    d.mkdir(exist_ok=True)
    (d / "gas_study.json").write_text(json.dumps(study))

    with patch("proof_client.gas_study.run_gas_study", return_value=study):
        r3 = client.post("/dashboard/gas-study",
                         data={"network": "anvil", "batch_size": "2",
                               "confirm": "1", "include_merkle": "1"})
        check("T33 confirmed run → 200", r3.status_code == 200,
              str(r3.status_code))
        check("T34 detail page rendered", "gas_study_dash_ran" in r3.text)
        check("T35 savings banner shown", "saves" in r3.text)


# ══════════════════════════════════════════════════════════════════
# 6. Gas studies list + detail
# ══════════════════════════════════════════════════════════════════


def test_gas_studies_pages():
    section("Gas Studies List & Detail")

    r = client.get("/dashboard/gas-studies")
    check("T36 GET /dashboard/gas-studies → 200", r.status_code == 200,
          str(r.status_code))
    check("T37 installed study listed", "gas_study_dash_ran" in r.text)

    r2 = client.get("/dashboard/gas-studies/gas_study_dash_ran")
    check("T38 detail page → 200", r2.status_code == 200, str(r2.status_code))
    check("T39 workflow table rendered",
          "single_file" in r2.text and "merkle_batch" in r2.text)
    check("T40 download links present",
          "format=csv" in r2.text and "format=pdf" in r2.text)

    r3 = client.get("/dashboard/gas-studies/gas_study_missing")
    check("T41 unknown study → 404 page", r3.status_code == 404)


# ══════════════════════════════════════════════════════════════════
# 7. Navigation and home
# ══════════════════════════════════════════════════════════════════


def test_navigation():
    section("Navigation & Home Cards")

    r = client.get("/")
    check("T42 home → 200", r.status_code == 200)
    check("T43 home links deployments", "/dashboard/deployments" in r.text)
    check("T44 home links gas studies", "/dashboard/gas-studies" in r.text)

    r2 = client.get("/dashboard/evidence")
    check("T45 nav includes Deploy link on other pages",
          "/dashboard/deployments" in r2.text)
    check("T46 nav includes Gas link on other pages",
          "/dashboard/gas-studies" in r2.text)


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print("  Stage 13 Dashboard Tests — Deploy & Gas Pages")
    print("=" * 60)

    test_deploy_page()
    test_deploy_submit()
    test_deployments_page()
    test_gas_study_page()
    test_gas_study_submit()
    test_gas_studies_pages()
    test_navigation()

    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  Stage 13 Dashboard Results: {_passed}/{total} passed, {_failed} failed")
    print(f"{'=' * 60}\n")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
