"""
test_stage13_gas_api.py — Stage 13 API test suite (gas study endpoints)

Tests:
  1. GET /gas/studies (list)
  2. GET /gas/studies/{study_id} (detail + summaries)
  3. GET /gas/studies/{study_id}/report (formats)
  4. POST /gas/studies/run (confirm guard, dry run, success)
  5. Study id path safety

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m api.test_stage13_gas_api
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

_TMP = Path(tempfile.mkdtemp(prefix="stage13_gas_api_"))
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
    print(f"  ⛽ {title}")
    print(f"{'━'*60}")


_STUDY = {
    "study_id": "gas_study_20260702_000001",
    "network_key": "base_sepolia",
    "network_display_name": "Base Sepolia",
    "chain_id": 84532,
    "contract_address": "0xC",
    "native_token_symbol": "ETH",
    "batch_size": 5,
    "workflows": ["single_file", "merkle_batch"],
    "created_at_utc": "2026-07-02T00:00:00+00:00",
    "records": (
        [{"workflow": "single_file", "file_count": 1, "gas_used": 50_000,
          "total_fee_wei": 50_000 * 10**9, "total_fee_eth": "0.00005",
          "transaction_hash": "0x" + f"{i:02d}" * 32, "block_number": i}
         for i in range(1, 6)]
        + [{"workflow": "merkle_batch", "file_count": 5, "gas_used": 55_000,
            "total_fee_wei": 55_000 * 10**9, "total_fee_eth": "0.000055",
            "transaction_hash": "0x" + "ff" * 32, "block_number": 6}]
    ),
}


def _install_study():
    d = _STUDIES / _STUDY["study_id"]
    d.mkdir(exist_ok=True)
    (d / "gas_study.json").write_text(json.dumps(_STUDY))
    (d / "gas_study.md").write_text("# report")
    (d / "gas_study.csv").write_text("study_id\ntest\n")
    return d


# ══════════════════════════════════════════════════════════════════
# 1. GET /gas/studies
# ══════════════════════════════════════════════════════════════════


def test_list_studies():
    section("GET /gas/studies")

    r = client.get("/gas/studies")
    check("T01 GET /gas/studies → 200", r.status_code == 200, str(r.status_code))
    j = r.json()
    check("T02 status ok", j.get("status") == "ok")
    check("T03 empty list initially", j.get("count") == 0)

    _install_study()
    # A directory without gas_study.json must be ignored
    (_STUDIES / "not_a_study").mkdir(exist_ok=True)

    r2 = client.get("/gas/studies")
    j2 = r2.json()
    check("T04 lists installed study", j2["count"] == 1)
    s = j2["studies"][0]
    check("T05 summary has study_id", s["study_id"] == _STUDY["study_id"])
    check("T06 summary has network", s["network_key"] == "base_sepolia")
    check("T07 summary has tx_count", s["tx_count"] == 6)
    check("T08 summary has workflows",
          s["workflows"] == ["single_file", "merkle_batch"])


# ══════════════════════════════════════════════════════════════════
# 2. GET /gas/studies/{study_id}
# ══════════════════════════════════════════════════════════════════


def test_get_study():
    section("GET /gas/studies/{study_id}")
    _install_study()

    r = client.get(f"/gas/studies/{_STUDY['study_id']}")
    check("T09 study detail → 200", r.status_code == 200, str(r.status_code))
    j = r.json()
    check("T10 full study returned",
          j["study"]["study_id"] == _STUDY["study_id"])
    check("T11 summaries included",
          "single_file" in j["summaries"] and "merkle_batch" in j["summaries"])
    check("T12 summary aggregates txs",
          j["summaries"]["single_file"]["tx_count"] == 5)
    check("T13 merkle savings computed",
          abs(j["merkle_savings_percentage"] - 78.0) < 0.01)

    r2 = client.get("/gas/studies/gas_study_nonexistent")
    check("T14 unknown study → 404", r2.status_code == 404)
    check("T15 404 error envelope", r2.json().get("status") == "error")

    r3 = client.get("/gas/studies/..%2Fescape")
    check("T16 path traversal rejected", r3.status_code in (400, 404))


# ══════════════════════════════════════════════════════════════════
# 3. GET /gas/studies/{study_id}/report
# ══════════════════════════════════════════════════════════════════


def test_get_report():
    section("GET /gas/studies/{study_id}/report")
    _install_study()
    sid = _STUDY["study_id"]

    r = client.get(f"/gas/studies/{sid}/report")
    check("T17 default format md → 200", r.status_code == 200, str(r.status_code))
    check("T18 md content returned", "# report" in r.text)

    r2 = client.get(f"/gas/studies/{sid}/report", params={"format": "json"})
    check("T19 json format → 200", r2.status_code == 200)
    check("T20 json content correct",
          json.loads(r2.text)["study_id"] == sid)

    r3 = client.get(f"/gas/studies/{sid}/report", params={"format": "csv"})
    check("T21 csv format → 200", r3.status_code == 200)

    r4 = client.get(f"/gas/studies/{sid}/report", params={"format": "pdf"})
    check("T22 missing pdf → 404", r4.status_code == 404)

    r5 = client.get(f"/gas/studies/{sid}/report", params={"format": "exe"})
    check("T23 unknown format → 400", r5.status_code == 400)

    r6 = client.get("/gas/studies/nope/report")
    check("T24 unknown study report → 404", r6.status_code == 404)


# ══════════════════════════════════════════════════════════════════
# 4. POST /gas/studies/run
# ══════════════════════════════════════════════════════════════════


def test_run_study():
    section("POST /gas/studies/run")

    r = client.post("/gas/studies/run", json={"network": "anvil"})
    check("T25 no confirm → 400", r.status_code == 400, str(r.status_code))
    j = r.json()
    check("T26 error envelope", j.get("status") == "error")
    check("T27 message explains confirm requirement",
          "confirm=true" in j.get("message", ""))

    r2 = client.post("/gas/studies/run",
                     json={"network": "anvil", "confirm": False})
    check("T28 confirm=false → 400", r2.status_code == 400)

    # dry run does not require confirm
    fake_study = {"study_id": "gas_study_dry", "dry_run": True, "records": []}
    with patch("proof_client.gas_study.run_gas_study",
               return_value=fake_study) as mock_run:
        r3 = client.post("/gas/studies/run",
                         json={"network": "anvil", "dry_run": True})
        check("T29 dry run without confirm → 200", r3.status_code == 200,
              str(r3.status_code))
        check("T30 dry_run forwarded",
              mock_run.call_args.kwargs.get("dry_run") is True)

    # confirmed run
    fake_study2 = {"study_id": "gas_study_ran", "dry_run": False,
                   "records": [], "study_dir": "/tmp/x"}
    with patch("proof_client.gas_study.run_gas_study",
               return_value=fake_study2) as mock_run:
        r4 = client.post("/gas/studies/run",
                         json={"network": "base-sepolia", "confirm": True,
                               "batch_size": 10, "include_ipfs": True})
        check("T31 confirmed run → 200", r4.status_code == 200,
              str(r4.status_code))
        check("T32 study returned",
              r4.json()["study"]["study_id"] == "gas_study_ran")
        kwargs = mock_run.call_args.kwargs
        check("T33 batch_size forwarded", kwargs.get("batch_size") == 10)
        check("T34 include_ipfs forwarded", kwargs.get("include_ipfs") is True)
        check("T35 network forwarded", kwargs.get("network_key") == "base-sepolia")

    # errors surface as 400
    with patch("proof_client.gas_study.run_gas_study",
               side_effect=ValueError("Missing contract address for 'anvil'.")):
        r5 = client.post("/gas/studies/run",
                         json={"network": "anvil", "confirm": True})
        check("T36 ValueError → 400", r5.status_code == 400)
        check("T37 error message surfaced",
              "Missing contract address" in r5.json()["message"])


# ══════════════════════════════════════════════════════════════════
# 5. OpenAPI
# ══════════════════════════════════════════════════════════════════


def test_openapi():
    section("OpenAPI Paths")

    paths = client.get("/openapi.json").json()["paths"]
    check("T38 /gas/studies documented", "/gas/studies" in paths)
    check("T39 /gas/studies/{study_id} documented",
          "/gas/studies/{study_id}" in paths)
    check("T40 /gas/studies/{study_id}/report documented",
          "/gas/studies/{study_id}/report" in paths)
    check("T41 /gas/studies/run documented", "/gas/studies/run" in paths)


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print("  Stage 13 API Tests — Gas Study Endpoints")
    print("=" * 60)

    test_list_studies()
    test_get_study()
    test_get_report()
    test_run_study()
    test_openapi()

    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  Stage 13 Gas API Results: {_passed}/{total} passed, {_failed} failed")
    print(f"{'=' * 60}\n")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
