"""
test_stage12_networks_api.py — Stage 12 API test suite (network endpoints)

Tests:
  1.  GET /networks
  2.  GET /networks/current
  3.  GET /networks/{network_key}
  4.  Network param in register / verify / batch endpoints
  5.  Backward compatibility (old endpoints still work without network)

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m api.test_stage12_networks_api
"""

import hashlib
import json
import os
import sys
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# ── Test-isolation setup ──────────────────────────────────────────

import proof_client.config as config
import proof_client.evidence_repository as repo
import proof_client.evidence_store as store
import proof_client.register_file as register_mod
import proof_client.verify_file as verify_mod
import proof_client.batch_merkle_register as batch_mod

_TMP = Path(tempfile.mkdtemp(prefix="stage12_api_"))
config.UPLOADS_DIR = _TMP / "uploads"
config.API_TEMP_DIR = _TMP / "api_tmp"
config.PACKAGES_DIR = _TMP / "packages"
config.EVIDENCE_DIR = _TMP / "evidence"
for _d in (config.UPLOADS_DIR, config.API_TEMP_DIR, config.PACKAGES_DIR, config.EVIDENCE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

repo.DB_PATH = _TMP / "evidence.db"
store.EVIDENCE_DIR = config.EVIDENCE_DIR

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
    print(f"  🌐 {title}")
    print(f"{'━'*60}")


_MOCK_TX = {
    "tx_hash": "cc" * 32,
    "block_number": 5000,
    "gas_used": 25000,
    "status": "success",
    "contract_address": "",
    "network_key": None,
}
_MOCK_ADDR = "0x000000000000000000000000000000000000dEaD"


def _install_mocks():
    register_mod.register_hash = lambda fh, uri, network_key=None: dict(_MOCK_TX)
    register_mod.get_address = lambda: _MOCK_ADDR
    verify_mod.verify_hash = lambda fh, network_key=None: {
        "owner": _MOCK_ADDR, "timestamp": 1700000000, "uri": "x", "registered": True
    }


def _upload(name: str, content: bytes):
    return {"file": (name, content, "application/octet-stream")}


def _sha256(data: bytes) -> str:
    return "0x" + hashlib.sha256(data).hexdigest()


# ══════════════════════════════════════════════════════════════════
# 1. GET /networks
# ══════════════════════════════════════════════════════════════════


def test_list_networks():
    section("GET /networks")

    r = client.get("/networks")
    check("T01 GET /networks → 200", r.status_code == 200, str(r.status_code))
    j = r.json()
    check("T02 status is ok", j.get("status") == "ok")
    check("T03 has count field", "count" in j)
    check("T04 has networks list", isinstance(j.get("networks"), list))
    check("T05 count matches list length", j["count"] == len(j["networks"]))
    check("T06 count >= 3", j["count"] >= 3)

    keys = [n["network_key"] for n in j["networks"]]
    check("T07 sepolia in networks", "sepolia" in keys)
    check("T08 anvil in networks", "anvil" in keys)
    check("T09 base_sepolia in networks", "base_sepolia" in keys)

    sepolia = next((n for n in j["networks"] if n["network_key"] == "sepolia"), None)
    check("T10 sepolia has display_name", bool(sepolia and sepolia.get("display_name")))
    check("T11 sepolia has chain_id 11155111", sepolia and sepolia.get("chain_id") == 11155111)
    check("T12 sepolia has is_testnet", sepolia and sepolia.get("is_testnet") is True)


# ══════════════════════════════════════════════════════════════════
# 2. GET /networks/current
# ══════════════════════════════════════════════════════════════════


def test_current_network():
    section("GET /networks/current")

    original = os.environ.get("DEFAULT_NETWORK")
    try:
        os.environ["DEFAULT_NETWORK"] = "sepolia"
        r = client.get("/networks/current")
        check("T13 GET /networks/current → 200", r.status_code == 200, str(r.status_code))
        j = r.json()
        check("T14 status is ok", j.get("status") == "ok")
        check("T15 network_key is sepolia", j.get("network_key") == "sepolia")
        check("T16 has display_name", bool(j.get("display_name")))
        check("T17 has chain_id", isinstance(j.get("chain_id"), int))
        check("T18 has is_testnet", "is_testnet" in j)
        check("T19 has explorer_base_url", "explorer_base_url" in j)
    finally:
        if original is not None:
            os.environ["DEFAULT_NETWORK"] = original
        elif "DEFAULT_NETWORK" in os.environ:
            del os.environ["DEFAULT_NETWORK"]


# ══════════════════════════════════════════════════════════════════
# 3. GET /networks/{network_key}
# ══════════════════════════════════════════════════════════════════


def test_get_network_by_key():
    section("GET /networks/{network_key}")

    r = client.get("/networks/sepolia")
    check("T20 GET /networks/sepolia → 200", r.status_code == 200, str(r.status_code))
    j = r.json()
    check("T21 status is ok", j.get("status") == "ok")
    check("T22 network_key is sepolia", j.get("network_key") == "sepolia")
    check("T23 chain_id is 11155111", j.get("chain_id") == 11155111)
    check("T24 has explorer_base_url", bool(j.get("explorer_base_url")))
    check("T25 is_testnet is True", j.get("is_testnet") is True)

    r2 = client.get("/networks/anvil")
    check("T26 GET /networks/anvil → 200", r2.status_code == 200)
    j2 = r2.json()
    check("T27 anvil chain_id 31337", j2.get("chain_id") == 31337)

    r3 = client.get("/networks/base_sepolia")
    check("T28 GET /networks/base_sepolia → 200", r3.status_code == 200)
    j3 = r3.json()
    check("T29 base_sepolia chain_id 84532", j3.get("chain_id") == 84532)

    # Hyphen form should also work
    r4 = client.get("/networks/base-sepolia")
    check("T30 GET /networks/base-sepolia → 200", r4.status_code == 200)
    j4 = r4.json()
    check("T31 base-sepolia resolves to base_sepolia", j4.get("network_key") == "base_sepolia")

    # Unknown network → 404
    r5 = client.get("/networks/unknown_xyz")
    check("T32 unknown network → 404", r5.status_code == 404)
    check("T33 unknown network error envelope", r5.json().get("status") == "error")


# ══════════════════════════════════════════════════════════════════
# 4. Network param in register endpoints
# ══════════════════════════════════════════════════════════════════


def test_register_with_network():
    section("Register Endpoints with Network Param")
    _install_mocks()

    content = b"stage 12 api register with network"
    r = client.post(
        "/register/file",
        files=_upload("stage12_reg.txt", content),
        data={"network": "sepolia"},
    )
    check("T34 POST /register/file?network=sepolia → 200", r.status_code == 200, str(r.status_code))
    j = r.json()
    check("T35 register returns file_hash", bool(j.get("file_hash")))
    check("T36 register returns status ok", j.get("status") == "ok")

    # Without network (backward compat)
    content2 = b"stage 12 api register no network"
    r2 = client.post(
        "/register/file",
        files=_upload("stage12_reg2.txt", content2),
    )
    check("T37 POST /register/file no network → 200", r2.status_code == 200, str(r2.status_code))

    # IPFS variant with network
    content3 = b"stage 12 ipfs with network"
    r3 = client.post(
        "/register/file/ipfs",
        files=_upload("stage12_ipfs.txt", content3),
        data={"network": "sepolia", "ipfs_provider": "mock"},
    )
    check("T38 POST /register/file/ipfs with network → 200", r3.status_code == 200, str(r3.status_code))

    # Encrypted IPFS with network
    content4 = b"stage 12 enc ipfs with network"
    r4 = client.post(
        "/register/file/encrypted-ipfs",
        files=_upload("stage12_enc.txt", content4),
        data={"network": "sepolia", "ipfs_provider": "mock", "password": "testpass123"},
    )
    check("T39 POST /register/file/encrypted-ipfs with network → 200", r4.status_code == 200, str(r4.status_code))


# ══════════════════════════════════════════════════════════════════
# 5. Network param in verify endpoints
# ══════════════════════════════════════════════════════════════════


def test_verify_with_network():
    section("Verify Endpoints with Network Param")
    _install_mocks()

    content = b"stage 12 verify with network"
    r = client.post(
        "/verify/file",
        files=_upload("stage12_verify.txt", content),
        data={"network": "sepolia"},
    )
    check("T40 POST /verify/file with network → 200", r.status_code == 200, str(r.status_code))
    j = r.json()
    check("T41 verify returns status ok", j.get("status") == "ok")

    # Without network
    r2 = client.post(
        "/verify/file",
        files=_upload("stage12_verify2.txt", content),
    )
    check("T42 POST /verify/file no network → 200", r2.status_code == 200, str(r2.status_code))


# ══════════════════════════════════════════════════════════════════
# 6. Network param in batch endpoints
# ══════════════════════════════════════════════════════════════════


def test_batch_with_network():
    section("Batch Endpoints with Network Param")

    # Mock run_batch_registration to accept network_key
    def _fake_batch(folder, title="", author="", description="", recursive=False, dry_run=False, network_key=None):
        return {
            "batch_id": "batch-stage12",
            "merkle_root": "0x" + "dd" * 32,
            "uri": "batch://batch-stage12",
            "file_count": 1,
            "transaction_hash": "0x" + "ee" * 32,
            "explorer_url": "",
            "package_zip": Path("/tmp/pkg12.zip"),
        }

    batch_mod.run_batch_registration = _fake_batch

    folder = _TMP / "batch12"
    folder.mkdir(exist_ok=True)
    (folder / "doc.txt").write_bytes(b"doc content")

    r = client.post(
        "/batches/merkle/register",
        data={"folder_path": str(folder), "network": "base_sepolia"},
    )
    check("T43 POST /batches/merkle/register with network → 200", r.status_code == 200, str(r.status_code))
    j = r.json()
    check("T44 batch register status ok", j.get("status") == "ok")
    check("T45 batch register returns batch_id", j.get("batch_id") == "batch-stage12")


# ══════════════════════════════════════════════════════════════════
# 7. Dashboard network-aware pages
# ══════════════════════════════════════════════════════════════════


def test_dashboard_network_pages():
    section("Dashboard Network-Aware Pages")

    # Home shows network badge
    r = client.get("/")
    check("T46 GET / → 200", r.status_code == 200)

    # Register page has network selector
    r2 = client.get("/dashboard/register")
    check("T47 GET /dashboard/register → 200", r2.status_code == 200)
    check("T48 register page has network selector", 'name="network"' in r2.text)

    # Verify page has network selector
    r3 = client.get("/dashboard/verify")
    check("T49 GET /dashboard/verify → 200", r3.status_code == 200)
    check("T50 verify page has network selector", 'name="network"' in r3.text)

    # Verify merkle page has network selector
    r4 = client.get("/dashboard/verify-merkle")
    check("T51 GET /dashboard/verify-merkle → 200", r4.status_code == 200)
    check("T52 verify-merkle page has network selector", 'name="network"' in r4.text)


# ══════════════════════════════════════════════════════════════════
# 8. OpenAPI docs include network endpoints
# ══════════════════════════════════════════════════════════════════


def test_openapi_includes_networks():
    section("OpenAPI includes /networks")

    paths = client.get("/openapi.json").json()["paths"]
    check("T53 /networks in OpenAPI paths", "/networks" in paths)
    check("T54 /networks/current in OpenAPI paths", "/networks/current" in paths)
    check("T55 /networks/{network_key} in OpenAPI paths",
          "/networks/{network_key}" in paths)


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print("  Stage 12 API Tests — Network Endpoints")
    print("=" * 60)

    test_list_networks()
    test_current_network()
    test_get_network_by_key()
    test_register_with_network()
    test_verify_with_network()
    test_batch_with_network()
    test_dashboard_network_pages()
    test_openapi_includes_networks()

    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  Stage 12 API Results: {_passed}/{total} passed, {_failed} failed")
    print(f"{'=' * 60}\n")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
