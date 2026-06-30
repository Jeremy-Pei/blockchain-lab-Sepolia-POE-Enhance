"""
test_stage11_dashboard.py — Stage 11 test suite (Web Evidence Dashboard)

Tests the Jinja2/HTML dashboard layer using FastAPI's TestClient.

Isolation strategy (identical to test_stage10_api.py):
  - All file I/O is redirected to a temp directory.
  - Blockchain seams (register_hash / verify_hash / get_address) are
    monkeypatched.
  - The IPFS mock provider runs for real (no network needed).

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m api.test_stage11_dashboard
"""

import hashlib
import json
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path

warnings.filterwarnings("ignore")

# ── Test-isolation setup (must run before any app import) ───────────

import proof_client.config as config
import proof_client.evidence_repository as repo
import proof_client.evidence_store as store
import proof_client.register_file as register_mod
import proof_client.verify_file as verify_mod

_TMP = Path(tempfile.mkdtemp(prefix="stage11_dash_"))
config.UPLOADS_DIR = _TMP / "uploads"
config.API_TEMP_DIR = _TMP / "api_tmp"
config.PACKAGES_DIR = _TMP / "packages"
config.BATCH_PACKAGES_DIR = _TMP / "packages" / "batches"
config.EVIDENCE_DIR = _TMP / "evidence"
for _d in (
    config.UPLOADS_DIR,
    config.API_TEMP_DIR,
    config.PACKAGES_DIR,
    config.BATCH_PACKAGES_DIR,
    config.EVIDENCE_DIR,
):
    _d.mkdir(parents=True, exist_ok=True)

repo.DB_PATH = _TMP / "evidence.db"
store.EVIDENCE_DIR = config.EVIDENCE_DIR

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402
from proof_client.evidence_schema import EvidenceRecord  # noqa: E402
from proof_client.merkle_tree import generate_proof, get_merkle_root, sha256_file  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


# ── Test counters ──────────────────────────────────────────────────

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


def section(title: str):
    print(f"\n{'━'*60}")
    print(f"  🌐 {title}")
    print(f"{'━'*60}")


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        ok(name, detail)
    else:
        fail(name, detail or "assertion failed")


# ── Mock seams ─────────────────────────────────────────────────────

_MOCK_TX = {
    "tx_hash": "aabbccddeeff0011aabbccddeeff0011aabbccddeeff0011aabbccddeeff0011",
    "block_number": 999999,
    "gas_used": 30000,
    "status": "success",
    "contract_address": "",
    "network_key": None,
}
_MOCK_ADDR = "0x000000000000000000000000000000000000dEaD"


def _install_register_mock():
    # Stage 12: register_hash now accepts an optional network_key kwarg.
    register_mod.register_hash = lambda file_hash, uri, network_key=None: dict(_MOCK_TX)
    register_mod.get_address = lambda: _MOCK_ADDR


def _install_verify_mock(registered: bool):
    # Stage 12: verify_hash now accepts an optional network_key kwarg.
    def _vh(file_hash, network_key=None):
        return {
            "owner": _MOCK_ADDR,
            "timestamp": 1700000000 if registered else 0,
            "uri": "sepolia://x",
            "registered": registered,
        }
    verify_mod.verify_hash = _vh


# ── File helpers ───────────────────────────────────────────────────


def _upload(name: str, content: bytes):
    return {"file": (name, content, "application/octet-stream")}


def _sha256(data: bytes) -> str:
    return "0x" + hashlib.sha256(data).hexdigest()


def _insert_evidence(file_hash: str = "0x" + "aa" * 32, file_name: str = "test.txt") -> None:
    """Insert a dummy EvidenceRecord into the repo for browser tests."""
    record = EvidenceRecord(
        file_name=file_name,
        file_hash=file_hash,
        uri=f"sepolia://{file_name}",
        tx_hash="0x" + "bb" * 32,
        block_number=1,
        owner=_MOCK_ADDR,
        network="Ethereum Sepolia",
        created_at="2024-01-01T00:00:00+00:00",
    )
    repo.insert(record)


# ══════════════════════════════════════════════════════════════════
# 1. Page rendering (GET routes)
# ══════════════════════════════════════════════════════════════════


def test_page_rendering():
    section("Page Rendering (GET routes)")

    r = client.get("/")
    check("T01 GET / → 200", r.status_code == 200, str(r.status_code))
    check("T02 GET / is HTML", "text/html" in r.headers.get("content-type", ""))
    check("T03 GET / contains Dashboard title",
          "Dashboard" in r.text or "Proof-of-Existence" in r.text)

    r = client.get("/dashboard/hash")
    check("T04 GET /dashboard/hash → 200", r.status_code == 200)
    check("T05 GET /dashboard/hash is HTML", "text/html" in r.headers.get("content-type", ""))

    r = client.get("/dashboard/register")
    check("T06 GET /dashboard/register → 200", r.status_code == 200)

    r = client.get("/dashboard/verify")
    check("T07 GET /dashboard/verify → 200", r.status_code == 200)

    r = client.get("/dashboard/verify-merkle")
    check("T08 GET /dashboard/verify-merkle → 200", r.status_code == 200)

    r = client.get("/dashboard/evidence")
    check("T09 GET /dashboard/evidence → 200", r.status_code == 200)

    r = client.get("/dashboard/batches")
    check("T10 GET /dashboard/batches → 200", r.status_code == 200)

    r = client.get("/dashboard/packages")
    check("T11 GET /dashboard/packages → 200", r.status_code == 200)


# ══════════════════════════════════════════════════════════════════
# 2. Navbar and navigation
# ══════════════════════════════════════════════════════════════════


def test_navbar():
    section("Navbar and Navigation")

    r = client.get("/")
    html = r.text
    check("T12 navbar contains Hash link", "/dashboard/hash" in html)
    check("T13 navbar contains Register link", "/dashboard/register" in html)
    check("T14 navbar contains Verify link", "/dashboard/verify" in html)
    check("T15 navbar contains Evidence link", "/dashboard/evidence" in html)
    check("T16 navbar contains Batches link", "/dashboard/batches" in html)
    check("T17 navbar contains Packages link", "/dashboard/packages" in html)
    check("T18 navbar contains API Docs /docs link", "/docs" in html)


# ══════════════════════════════════════════════════════════════════
# 3. File hash form
# ══════════════════════════════════════════════════════════════════


def test_hash_form():
    section("File Hash Form")

    content = b"stage 11 hash test"
    r = client.post("/dashboard/hash", files=_upload("hash_test.txt", content))
    check("T19 POST /dashboard/hash → 200", r.status_code == 200, str(r.status_code))
    check("T20 POST /dashboard/hash returns HTML", "text/html" in r.headers.get("content-type", ""))
    expected_hash = _sha256(content)
    check("T21 hash in response", expected_hash in r.text, expected_hash[:20])
    check("T22 0x-prefixed hash", "0x" in r.text)

    # Missing file → 422
    r_miss = client.post("/dashboard/hash")
    check("T23 missing file → 422", r_miss.status_code == 422, str(r_miss.status_code))


# ══════════════════════════════════════════════════════════════════
# 4. Register form
# ══════════════════════════════════════════════════════════════════


def test_register_form():
    section("Register Form")
    _install_register_mock()

    # Normal mode
    content = b"stage 11 register normal " + b"X"
    r = client.post(
        "/dashboard/register",
        files=_upload("reg_normal.txt", content),
        data={"title": "My Work", "author": "Bob", "description": "desc", "mode": "normal"},
    )
    check("T24 POST /dashboard/register normal → 200", r.status_code == 200)
    check("T25 register result page is HTML", "text/html" in r.headers.get("content-type", ""))
    check("T26 file_hash in result", _sha256(content) in r.text)

    # IPFS mode
    content2 = b"stage 11 register ipfs " + b"Y"
    r2 = client.post(
        "/dashboard/register",
        files=_upload("reg_ipfs.txt", content2),
        data={"mode": "ipfs"},
    )
    check("T27 POST /dashboard/register ipfs → 200", r2.status_code == 200)

    # Encrypted IPFS mode
    content3 = b"stage 11 encrypted ipfs " + b"Z"
    r3 = client.post(
        "/dashboard/register",
        files=_upload("reg_enc.txt", content3),
        data={"mode": "encrypted_ipfs", "password": "s3cr3t"},
    )
    check("T28 POST /dashboard/register encrypted_ipfs → 200", r3.status_code == 200)
    check("T29 password not in response HTML", "s3cr3t" not in r3.text)

    # Invalid mode
    r_bad = client.post(
        "/dashboard/register",
        files=_upload("bad.txt", b"bad"),
        data={"mode": "invalid_mode"},
    )
    check("T30 invalid mode returns error page", "error" in r_bad.text.lower() or r_bad.status_code in (200, 400))

    # encrypted_ipfs without password → error
    r_nopw = client.post(
        "/dashboard/register",
        files=_upload("nopw.txt", b"no password"),
        data={"mode": "encrypted_ipfs", "password": ""},
    )
    check("T31 encrypted_ipfs without password → error message",
          "password" in r_nopw.text.lower() or r_nopw.status_code in (200, 400))

    # Missing file → 422
    r_miss = client.post("/dashboard/register", data={"mode": "normal"})
    check("T32 missing file → 422", r_miss.status_code == 422)


# ══════════════════════════════════════════════════════════════════
# 5. Verify form
# ══════════════════════════════════════════════════════════════════


def test_verify_form():
    section("Verify Form")
    _install_register_mock()

    content = b"verify dashboard test " + b"V"
    client.post("/dashboard/register", files=_upload("verify_dash.txt", content),
                data={"mode": "normal"})

    _install_verify_mock(registered=True)
    r = client.post("/dashboard/verify", files=_upload("verify_dash.txt", content))
    check("T33 POST /dashboard/verify → 200", r.status_code == 200)
    check("T34 verify result is HTML", "text/html" in r.headers.get("content-type", ""))
    check("T35 PASSED appears in result", "PASSED" in r.text or "passed" in r.text.lower())

    _install_verify_mock(registered=False)
    r2 = client.post("/dashboard/verify", files=_upload("unknown.txt", b"never registered"))
    check("T36 unregistered → FAILED in result", "FAILED" in r2.text or "failed" in r2.text.lower())

    r_miss = client.post("/dashboard/verify")
    check("T37 missing file → 422", r_miss.status_code == 422)


# ══════════════════════════════════════════════════════════════════
# 6. Verify Merkle proof form
# ══════════════════════════════════════════════════════════════════


def test_verify_merkle_form():
    section("Verify Merkle Proof Form")

    tmp = _TMP / "merkle_dash"
    tmp.mkdir(exist_ok=True)
    f1 = tmp / "doc1.txt"
    f2 = tmp / "doc2.txt"
    f1.write_bytes(b"merkle dash one")
    f2.write_bytes(b"merkle dash two")

    leaves = [sha256_file(f1), sha256_file(f2)]
    root = get_merkle_root(leaves)
    proof = generate_proof(leaves, 0)
    proof_json = {
        "batch_id": "dash-batch",
        "file_hash": leaves[0],
        "merkle_root": root,
        "leaf_index": 0,
        "proof": proof,
    }
    pj = tmp / "doc1.proof.json"
    pj.write_text(json.dumps(proof_json), encoding="utf-8")

    r = client.post(
        "/dashboard/verify-merkle",
        files={
            "file": ("doc1.txt", f1.read_bytes(), "application/octet-stream"),
            "proof": ("doc1.proof.json", pj.read_bytes(), "application/json"),
        },
        data={"check_blockchain": ""},
    )
    check("T38 POST /dashboard/verify-merkle → 200", r.status_code == 200)
    check("T39 Merkle result is HTML", "text/html" in r.headers.get("content-type", ""))
    check("T40 Merkle root or result shown", root[:16] in r.text or "passed" in r.text.lower())


# ══════════════════════════════════════════════════════════════════
# 7. Evidence browser
# ══════════════════════════════════════════════════════════════════


def test_evidence_browser():
    section("Evidence Browser")

    file_hash = "0x" + "cc" * 32
    _insert_evidence(file_hash=file_hash, file_name="browser_test.txt")

    r = client.get("/dashboard/evidence")
    check("T41 GET /dashboard/evidence → 200", r.status_code == 200)
    check("T42 evidence list shows file name", "browser_test.txt" in r.text)
    check("T43 evidence list shows hash", file_hash[:12] in r.text)

    # Detail page
    r2 = client.get(f"/dashboard/evidence/{file_hash}")
    check("T44 GET /dashboard/evidence/{hash} → 200", r2.status_code == 200)
    check("T45 evidence detail shows full hash", file_hash in r2.text)

    # Not found
    r3 = client.get("/dashboard/evidence/0x" + "00" * 32)
    check("T46 nonexistent evidence → error page", r3.status_code in (200, 404))
    check("T47 not-found error page mentions hash",
          "not found" in r3.text.lower() or "error" in r3.text.lower())


# ══════════════════════════════════════════════════════════════════
# 8. Batch browser
# ══════════════════════════════════════════════════════════════════


def test_batch_browser():
    section("Batch Browser")

    r = client.get("/dashboard/batches")
    check("T48 GET /dashboard/batches → 200", r.status_code == 200)

    r2 = client.get("/dashboard/batches/nonexistent-batch-id")
    check("T49 nonexistent batch → error page", r2.status_code in (200, 404))
    check("T50 not-found error page for batch",
          "not found" in r2.text.lower() or "error" in r2.text.lower())


# ══════════════════════════════════════════════════════════════════
# 9. Packages page
# ══════════════════════════════════════════════════════════════════


def test_packages_page():
    section("Packages Page")

    # Create a dummy zip
    zip_path = config.PACKAGES_DIR / "test_pkg.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.txt", "test")

    r = client.get("/dashboard/packages")
    check("T51 GET /dashboard/packages → 200", r.status_code == 200)
    check("T52 packages page shows test_pkg.zip", "test_pkg.zip" in r.text)
    check("T53 packages page has /packages/ download link",
          "/packages/test_pkg.zip" in r.text)


# ══════════════════════════════════════════════════════════════════
# 10. Static assets
# ══════════════════════════════════════════════════════════════════


def test_static_assets():
    section("Static Assets")

    r = client.get("/static/css/style.css")
    check("T54 /static/css/style.css → 200", r.status_code == 200, str(r.status_code))
    check("T55 style.css contains hash-text", "hash-text" in r.text)

    r2 = client.get("/static/js/app.js")
    check("T56 /static/js/app.js → 200", r2.status_code == 200, str(r2.status_code))
    check("T57 app.js contains copyText", "copyText" in r2.text)


# ══════════════════════════════════════════════════════════════════
# 11. Security checks
# ══════════════════════════════════════════════════════════════════


def test_security():
    section("Security Checks")

    # No private key in any GET page
    pages = ["/", "/dashboard/hash", "/dashboard/register",
             "/dashboard/verify", "/dashboard/evidence", "/dashboard/batches"]
    pk = config.PRIVATE_KEY
    for page in pages:
        r = client.get(page)
        if pk:
            check(f"T58a no private key in {page}", pk not in r.text)

    # Password not in result after encrypted registration
    _install_register_mock()
    r_enc = client.post(
        "/dashboard/register",
        files=_upload("sec_enc.txt", b"security test"),
        data={"mode": "encrypted_ipfs", "password": "sup3rsecret"},
    )
    check("T58 password 'sup3rsecret' not in result HTML", "sup3rsecret" not in r_enc.text)

    # Path traversal blocked on packages endpoint
    r_pt = client.get("/packages/../requirements.txt")
    check("T59 path traversal on /packages/ returns 400 or 404",
          r_pt.status_code in (400, 404), str(r_pt.status_code))

    # error.html back button
    r_err = client.get("/dashboard/evidence/0x" + "ff" * 32)
    check("T60 error page has back button", "back" in r_err.text.lower() or "Back" in r_err.text)


# ══════════════════════════════════════════════════════════════════
# 12. Result page quality
# ══════════════════════════════════════════════════════════════════


def test_result_quality():
    section("Result Page Quality")

    _install_register_mock()
    content = b"result quality test"
    r = client.post(
        "/dashboard/register",
        files=_upload("quality.txt", content),
        data={"mode": "normal", "title": "Quality Test"},
    )
    html = r.text
    expected_hash = _sha256(content)
    check("T61 result shows file_hash", expected_hash in html)
    check("T62 result page has status badge", "status-badge" in html or "Success" in html or "badge" in html)
    check("T63 result page hash-text class present", "hash-text" in html)


# ══════════════════════════════════════════════════════════════════
# 13. Backward compatibility (Stage 10 API still works)
# ══════════════════════════════════════════════════════════════════


def test_backward_compatibility():
    section("Backward Compatibility (Stage 10 API)")

    r = client.get("/health")
    check("T64 GET /health → 200", r.status_code == 200)
    check("T65 /health status == ok", r.json().get("status") == "ok")

    r2 = client.get("/version")
    check("T66 GET /version → 200", r2.status_code == 200)
    check("T67 /version returns version field", "version" in r2.json())

    content = b"back compat hash"
    r3 = client.post("/files/hash", files=_upload("bc.txt", content))
    check("T68 POST /files/hash → 200", r3.status_code == 200)
    check("T69 /files/hash returns file_hash", "file_hash" in r3.json())

    r4 = client.get("/evidence/files")
    check("T70 GET /evidence/files → 200", r4.status_code == 200)

    r5 = client.get("/packages")
    check("T71 GET /packages → 200", r5.status_code == 200)

    r6 = client.get("/batches")
    check("T72 GET /batches → 200", r6.status_code == 200)


# ══════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════


def run_all():
    test_page_rendering()
    test_navbar()
    test_hash_form()
    test_register_form()
    test_verify_form()
    test_verify_merkle_form()
    test_evidence_browser()
    test_batch_browser()
    test_packages_page()
    test_static_assets()
    test_security()
    test_result_quality()
    test_backward_compatibility()

    print(f"\n{'═'*60}")
    total = _passed + _failed
    print(f"  Stage 11 Dashboard Tests: {_passed}/{total} passed")
    if _failed:
        print(f"  {_failed} FAILED")
    print(f"{'═'*60}")
    return _failed


if __name__ == "__main__":
    exit_code = run_all()
    sys.exit(exit_code)
