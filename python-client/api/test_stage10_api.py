"""
test_stage10_api.py — Stage 10 test suite (FastAPI evidence service)

Tests the HTTP API layer (api/) over the proof_client toolkit using
fastapi.testclient.TestClient.

Isolation strategy:
  - Evidence DB, evidence JSON dir, uploads dir and packages dir are all
    redirected to a temporary directory so tests never touch real data and the
    file_hash UNIQUE constraint cannot collide across reruns.
  - Blockchain seams (register_hash / verify_hash / get_address) and the heavy
    batch pipeline are monkeypatched; the IPFS "mock" provider and all crypto
    run for real (they are local / offline).

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m api.test_stage10_api
"""

import hashlib
import json
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path

# Silence the starlette/httpx TestClient deprecation noise.
warnings.filterwarnings("ignore")

# ── Test-isolation setup (must happen before app handles requests) ──

import proof_client.config as config
import proof_client.evidence_repository as repo
import proof_client.evidence_store as store
import proof_client.register_file as register_mod
import proof_client.verify_file as verify_mod
import proof_client.batch_merkle_register as batch_mod

_TMP = Path(tempfile.mkdtemp(prefix="stage10_api_"))
config.UPLOADS_DIR = _TMP / "uploads"
config.API_TEMP_DIR = _TMP / "api_tmp"
config.PACKAGES_DIR = _TMP / "packages"
config.EVIDENCE_DIR = _TMP / "evidence"
for _d in (config.UPLOADS_DIR, config.API_TEMP_DIR, config.PACKAGES_DIR, config.EVIDENCE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Redirect the persistence layers to the temp location.
repo.DB_PATH = _TMP / "evidence.db"
store.EVIDENCE_DIR = config.EVIDENCE_DIR

from fastapi.testclient import TestClient  # noqa: E402

from api import services  # noqa: E402
from api.main import app  # noqa: E402
from proof_client.evidence_schema import EvidenceRecord  # noqa: E402
from proof_client.merkle_tree import (  # noqa: E402
    generate_proof,
    get_merkle_root,
    sha256_file,
)

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
    "tx_hash": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "block_number": 123456,
    "gas_used": 21000,
    "status": "success",
    "contract_address": "",
    "network_key": None,
}
_MOCK_ADDRESS = "0x000000000000000000000000000000000000dEaD"


def _install_register_mock():
    # Stage 12: register_hash now accepts an optional network_key kwarg.
    register_mod.register_hash = lambda file_hash, uri, network_key=None: dict(_MOCK_TX)
    register_mod.get_address = lambda: _MOCK_ADDRESS


def _install_verify_mock(registered: bool):
    # Stage 12: verify_hash now accepts an optional network_key kwarg.
    def _vh(file_hash, network_key=None):
        return {
            "owner": _MOCK_ADDRESS,
            "timestamp": 1700000000 if registered else 0,
            "uri": "sepolia://x",
            "registered": registered,
        }

    verify_mod.verify_hash = _vh


# ── File helpers ───────────────────────────────────────────────────


def _upload(path: str, content: bytes):
    return {"file": (path, content, "application/octet-stream")}


def _sha256_hex(data: bytes) -> str:
    return "0x" + hashlib.sha256(data).hexdigest()


# ══════════════════════════════════════════════════════════════════
# 1. Health
# ══════════════════════════════════════════════════════════════════


def test_health():
    section("Health API")

    r = client.get("/health")
    check("T01 GET /health → 200", r.status_code == 200, str(r.status_code))
    check("T02 /health status == ok", r.json().get("status") == "ok")
    check("T03 /health service name", r.json().get("service") == "proof-of-existence-api")

    r = client.get("/version")
    j = r.json()
    check("T04 GET /version → 200", r.status_code == 200)
    check("T05 /version version == 0.10.0", j.get("version") == "0.10.0")
    check("T06 /version stage == Stage 10", j.get("stage") == "Stage 10")
    check("T07 /version name", j.get("name") == "FastAPI Evidence Service")


# ══════════════════════════════════════════════════════════════════
# 2. File hash
# ══════════════════════════════════════════════════════════════════


def test_file_hash():
    section("File Hash API")

    content = b"stage 10 hash test content"
    r = client.post("/files/hash", files=_upload("hash_me.txt", content))
    j = r.json()
    check("T08 POST /files/hash → 200", r.status_code == 200, str(r.status_code))
    check("T09 hash matches sha256", j.get("file_hash") == _sha256_hex(content))
    check("T10 hash is 0x-prefixed", str(j.get("file_hash", "")).startswith("0x"))
    check("T11 hash is 64 hex chars", len(j.get("file_hash", "")) == 66)
    check("T12 algorithm is SHA-256", j.get("file_hash_algorithm") == "SHA-256")
    check("T13 file_size_bytes correct", j.get("file_size_bytes") == len(content))

    saved = Path(j.get("saved_path", ""))
    check("T14 uploaded file saved under uploads/", saved.exists() and saved.parent == config.UPLOADS_DIR)

    # Missing file → 422 (FastAPI required-field validation)
    r = client.post("/files/hash")
    check("T15 /files/hash missing file → 422", r.status_code == 422, str(r.status_code))
    check("T16 422 envelope status == error", r.json().get("status") == "error")


# ══════════════════════════════════════════════════════════════════
# 3. Register
# ══════════════════════════════════════════════════════════════════


def test_register():
    section("Register API")
    _install_register_mock()

    content = b"register me on chain " + b"A"
    r = client.post(
        "/register/file",
        files=_upload("reg_plain.txt", content),
        data={"title": "My Paper", "author": "Alice", "description": "a test"},
    )
    j = r.json()
    check("T17 POST /register/file → 200", r.status_code == 200, str(r.status_code))
    check("T18 register status == ok", j.get("status") == "ok")
    check("T19 register returns file_hash", j.get("file_hash") == _sha256_hex(content))
    check("T20 register returns tx_hash", j.get("transaction_hash") == _MOCK_TX["tx_hash"])
    check("T21 register returns block_number", j.get("block_number") == 123456)
    check("T22 explorer_url built with 0x", "0x" + _MOCK_TX["tx_hash"] in (j.get("explorer_url") or ""))
    check("T23 note carries metadata", "Title: My Paper" in (j.get("record", {}).get("note") or ""))

    # Evidence is queryable afterwards
    r2 = client.get(f"/evidence/files/{j['file_hash']}")
    check("T24 registered evidence is queryable", r2.status_code == 200 and r2.json()["record"]["file_hash"] == j["file_hash"])

    # IPFS variant (mock provider, real local upload)
    content2 = b"register me with ipfs " + b"B"
    r = client.post(
        "/register/file/ipfs",
        files=_upload("reg_ipfs.txt", content2),
        data={"ipfs_provider": "mock"},
    )
    j = r.json()
    check("T25 POST /register/file/ipfs → 200", r.status_code == 200, str(r.status_code))
    check("T26 ipfs register has ipfs_uri", bool(j.get("ipfs_uri")))
    check("T27 ipfs uri is ipfs://", str(j.get("ipfs_uri", "")).startswith("ipfs://"))

    # Missing file → 422
    r = client.post("/register/file")
    check("T28 /register/file missing file → 422", r.status_code == 422)


# ══════════════════════════════════════════════════════════════════
# 4. Verify
# ══════════════════════════════════════════════════════════════════


def test_verify():
    section("Verify API")

    _install_register_mock()
    content = b"verify me content " + b"C"
    client.post("/register/file", files=_upload("verify_me.txt", content))

    _install_verify_mock(registered=True)
    r = client.post("/verify/file", files=_upload("verify_me.txt", content))
    j = r.json()
    check("T29 POST /verify/file → 200", r.status_code == 200, str(r.status_code))
    check("T30 verify passed == True", j.get("passed") is True)
    check("T31 verify has file_hash", j.get("file_hash") == _sha256_hex(content))
    check("T32 verify finds local evidence", j["details"]["local_evidence"] is not None)

    _install_verify_mock(registered=False)
    r = client.post("/verify/file", files=_upload("unknown.txt", b"never registered"))
    j = r.json()
    check("T33 unregistered verify passed == False", j.get("passed") is False)
    check("T34 unregistered message mentions NOT", "NOT" in j.get("message", ""))

    # Missing file → 422
    r = client.post("/verify/file")
    check("T35 /verify/file missing file → 422", r.status_code == 422)


# ══════════════════════════════════════════════════════════════════
# 5. Merkle proof verify (real crypto, no chain)
# ══════════════════════════════════════════════════════════════════


def _build_proof(tmp: Path):
    """Create two files + a valid proof.json for the first one."""
    f1 = tmp / "doc1.txt"
    f2 = tmp / "doc2.txt"
    f1.write_bytes(b"merkle doc one")
    f2.write_bytes(b"merkle doc two")
    leaves = [sha256_file(f1), sha256_file(f2)]
    root = get_merkle_root(leaves)
    proof = generate_proof(leaves, 0)
    proof_json = {
        "batch_id": "test-batch",
        "file_hash": leaves[0],
        "merkle_root": root,
        "leaf_index": 0,
        "proof": proof,
    }
    pj = tmp / "doc1.proof.json"
    pj.write_text(json.dumps(proof_json), encoding="utf-8")
    return f1, pj


def test_merkle_proof():
    section("Merkle Proof Verify API")

    tmp = _TMP / "merkle"
    tmp.mkdir(exist_ok=True)
    f1, pj = _build_proof(tmp)

    r = client.post(
        "/verify/merkle-proof",
        files={
            "file": ("doc1.txt", f1.read_bytes(), "application/octet-stream"),
            "proof": ("doc1.proof.json", pj.read_bytes(), "application/json"),
        },
        data={"chain": "false"},
    )
    j = r.json()
    check("T36 POST /verify/merkle-proof → 200", r.status_code == 200, str(r.status_code))
    check("T37 valid proof passed == True", j.get("passed") is True)

    # Tampered file → proof fails
    r = client.post(
        "/verify/merkle-proof",
        files={
            "file": ("doc1.txt", b"tampered content", "application/octet-stream"),
            "proof": ("doc1.proof.json", pj.read_bytes(), "application/json"),
        },
        data={"chain": "false"},
    )
    check("T38 tampered file fails verification", r.json().get("passed") is False)

    # Missing proof file → 422
    r = client.post("/verify/merkle-proof", files={"file": ("doc1.txt", b"x", "text/plain")})
    check("T39 missing proof → 422", r.status_code == 422)


# ══════════════════════════════════════════════════════════════════
# 6. Evidence query
# ══════════════════════════════════════════════════════════════════


def _insert_record(file_hash: str, name: str, tx: str) -> EvidenceRecord:
    rec = EvidenceRecord(
        file_name=name,
        file_hash=file_hash,
        uri=f"sepolia://{name}",
        tx_hash=tx,
        block_number=1,
        owner=_MOCK_ADDRESS,
        contract_address="0xC0",
        explorer_tx_url="https://sepolia.etherscan.io/tx/",
    )
    repo.insert(rec)
    return rec


def test_evidence_query():
    section("Evidence Query API")

    h1 = _sha256_hex(b"evidence query one")
    _insert_record(h1, "eq1.txt", "aaa1")

    r = client.get("/evidence/files?limit=50")
    j = r.json()
    check("T40 GET /evidence/files → 200", r.status_code == 200)
    check("T41 evidence list has status", j.get("status") == "ok")
    check("T42 evidence list count matches records", j.get("count") == len(j.get("records", [])))
    check("T43 evidence list non-empty", j.get("count") >= 1)

    r = client.get(f"/evidence/files/{h1}")
    check("T44 GET evidence by hash → 200", r.status_code == 200 and r.json()["record"]["file_hash"] == h1)

    r = client.get("/evidence/files/0xdoesnotexist")
    check("T45 evidence by missing hash → 404", r.status_code == 404)
    check("T46 404 envelope status == error", r.json().get("status") == "error")

    r = client.get("/evidence/tx/aaa1")
    check("T47 GET evidence by tx → 200", r.status_code == 200 and r.json()["record"]["file_hash"] == h1)

    r = client.get("/evidence/tx/nope")
    check("T48 evidence by missing tx → 404", r.status_code == 404)


# ══════════════════════════════════════════════════════════════════
# 7. Batch evidence query + register
# ══════════════════════════════════════════════════════════════════


def _insert_batch(batch_id: str, root: str):
    repo.insert_batch_evidence(
        {
            "batch_id": batch_id,
            "merkle_root": root,
            "file_count": 2,
            "transaction_hash": "0xbatchtx" + root[-4:],
            "created_at_utc": "2026-06-28T00:00:00+00:00",
        }
    )


def test_batches():
    section("Batch API")

    _insert_batch("batch-001", _sha256_hex(b"batch root one"))

    r = client.get("/batches")
    j = r.json()
    check("T49 GET /batches → 200", r.status_code == 200)
    check("T50 batch list has status", j.get("status") == "ok")
    check("T51 batch list count matches", j.get("count") == len(j.get("records", [])))

    r = client.get("/batches/batch-001")
    check("T52 GET batch by id → 200", r.status_code == 200 and r.json()["record"]["batch_id"] == "batch-001")

    r = client.get("/batches/nope")
    check("T53 missing batch → 404", r.status_code == 404)

    # Evidence-namespaced batch endpoints also work
    r = client.get("/evidence/batches")
    check("T54 GET /evidence/batches → 200", r.status_code == 200 and r.json().get("status") == "ok")

    # Register: invalid folder → 400
    r = client.post("/batches/merkle/register", data={"folder_path": "/no/such/folder/here"})
    check("T55 batch register invalid folder → 400", r.status_code == 400)

    # Register happy path with the batch pipeline mocked
    # Stage 12: run_batch_registration now accepts an optional network_key kwarg.
    def _fake_run(folder, title="", author="", description="", recursive=False, dry_run=False, network_key=None):
        return {
            "batch_id": "batch-xyz",
            "merkle_root": "0xroot",
            "uri": "batch://batch-xyz",
            "file_count": 3,
            "transaction_hash": "0xtx",
            "explorer_url": "https://x/tx/0xtx",
            "package_zip": Path("/tmp/pkg.zip"),
        }

    batch_mod.run_batch_registration = _fake_run
    folder = _TMP / "batch_src"
    folder.mkdir(exist_ok=True)
    (folder / "a.txt").write_bytes(b"a")
    r = client.post("/batches/merkle/register", data={"folder_path": str(folder)})
    j = r.json()
    check("T56 batch register (mocked) → 200", r.status_code == 200, str(r.status_code))
    check("T57 batch register returns batch_id", j.get("batch_id") == "batch-xyz")
    check("T58 batch register returns merkle_root", j.get("merkle_root") == "0xroot")
    check("T59 batch register file_count", j.get("file_count") == 3)
    check("T60 batch register status ok", j.get("status") == "ok")


# ══════════════════════════════════════════════════════════════════
# 8. Packages
# ══════════════════════════════════════════════════════════════════


def test_packages():
    section("Package API")

    # Export with no evidence → 404
    r = client.post("/packages/export", data={"file_hash": "0xnoevidence"})
    check("T61 export unknown hash → 404", r.status_code == 404)
    check("T62 export 404 envelope status error", r.json().get("status") == "error")

    # Export a real registered record
    _install_register_mock()
    content = b"package me content " + b"P"
    reg = client.post("/register/file", files=_upload("pkg_me.txt", content)).json()
    r = client.post("/packages/export", data={"file_hash": reg["file_hash"]})
    j = r.json()
    check("T63 POST /packages/export → 200", r.status_code == 200, str(r.status_code))
    check("T64 export returns package_name", bool(j.get("package_name")))
    check("T65 export zip exists", Path(j.get("zip_path", "/nope")).exists())

    zip_name = j["zip_name"]

    # List packages
    r = client.get("/packages")
    lj = r.json()
    check("T66 GET /packages → 200", r.status_code == 200 and lj.get("status") == "ok")
    check("T67 package list includes exported zip", any(p["package_name"] == zip_name for p in lj.get("packages", [])))

    # Download the real package
    r = client.get(f"/packages/{zip_name}")
    check("T68 download package → 200", r.status_code == 200)
    check("T69 download is a valid zip", r.content[:2] == b"PK")

    # Missing package → 404
    r = client.get("/packages/nonexistent_package.zip")
    check("T70 download missing → 404", r.status_code == 404)

    # Path traversal guards
    r = client.get("/packages/evil..name.zip")
    check("T71 download '..' name → 400", r.status_code == 400)
    r = client.get("/packages/evil%5Cname.zip")
    check("T72 download backslash name → 400", r.status_code == 400)


# ══════════════════════════════════════════════════════════════════
# 9. Security boundary
# ══════════════════════════════════════════════════════════════════


def test_security():
    section("Security Boundary")

    _install_register_mock()
    content = b"secret document contents " + b"S"
    password = "sup3r-s3cret-passw0rd"
    r = client.post(
        "/register/file/encrypted-ipfs",
        files=_upload("secret.txt", content),
        data={"password": password, "ipfs_provider": "mock"},
    )
    body = r.text
    j = r.json()
    check("T73 encrypted register → 200", r.status_code == 200, str(r.status_code))
    check("T74 password NOT in response body", password not in body)
    check("T75 'password' key NOT in response json", "password" not in j)
    check("T76 record marked encrypted", j.get("is_encrypted") is True)
    check("T77 original hash still registered", j.get("file_hash") == _sha256_hex(content))

    # Empty password rejected
    r = client.post(
        "/register/file/encrypted-ipfs",
        files=_upload("secret2.txt", b"x"),
        data={"password": "", "ipfs_provider": "mock"},
    )
    check("T78 empty password → 400/422", r.status_code in (400, 422))


# ══════════════════════════════════════════════════════════════════
# 10. Error handling + backward compatibility
# ══════════════════════════════════════════════════════════════════


def test_error_and_compat():
    section("Error Handling & Backward Compatibility")

    # Unified error envelope
    r = client.get("/evidence/files/0xmissing")
    j = r.json()
    check("T79 error envelope has status field", j.get("status") == "error")
    check("T80 error envelope has message field", "message" in j)

    # All success responses carry a status field
    statuses = []
    for path in ("/health", "/version", "/evidence/files", "/evidence/batches", "/packages", "/batches"):
        statuses.append(client.get(path).json().get("status"))
    check("T81 all GET responses have status==ok", all(s == "ok" for s in statuses), str(statuses))

    # OpenAPI surface
    paths = client.get("/openapi.json").json()["paths"]
    check("T82 OpenAPI exposes >= 18 paths", len(paths) >= 18, str(len(paths)))
    check("T83 /docs is served", client.get("/docs").status_code == 200)

    # Backward compatibility: register_file still accepts the new note kwarg
    import inspect

    sig = inspect.signature(register_mod.register_file)
    check("T84 register_file has note param", "note" in sig.parameters)

    # config exposes the Stage 10 dirs
    check("T85 config exposes UPLOADS_DIR", hasattr(config, "UPLOADS_DIR"))
    check("T86 config exposes API_TEMP_DIR", hasattr(config, "API_TEMP_DIR"))

    # services workflow functions exist and are callable
    for fn in ("register_file_workflow", "verify_file_workflow", "export_package_workflow", "batch_merkle_register_workflow"):
        check(f"T87 services.{fn} exists", callable(getattr(services, fn, None)))


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print("  Stage 10 Test Suite — FastAPI Evidence Service")
    print("=" * 60)

    test_health()
    test_file_hash()
    test_register()
    test_verify()
    test_merkle_proof()
    test_evidence_query()
    test_batches()
    test_packages()
    test_security()
    test_error_and_compat()

    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  Results: {_passed}/{total} passed, {_failed} failed")
    print(f"{'=' * 60}\n")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
