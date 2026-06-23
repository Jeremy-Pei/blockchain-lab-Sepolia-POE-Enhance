"""
test_stage7.py — Stage 7 test suite (IPFS integration)

Tests the off-chain content-addressed storage layer: CID/URI/gateway
formatting, the mock IPFS client (upload/download/hash invariance), the
EvidenceRecord IPFS fields, register_file argument parsing, IPFS sections in
the certificate / verification guide, evidence-package IPFS metadata, and the
verify_ipfs success/failure paths.

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m proof_client.test_stage7
"""

import json
import sys
import tempfile
from pathlib import Path

# ══════════════════════════════════════════════════════════════════
# Test helpers (same style as test_stage6.py)
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
    print(f"  🌀 {title}")
    print(f"{'━'*60}")


# ── Shared fixtures ────────────────────────────────────────────────

def _make_record(with_ipfs: bool = False):
    """Return an EvidenceRecord, optionally populated with IPFS fields."""
    from proof_client.evidence_schema import EvidenceRecord
    rec = EvidenceRecord(
        file_name="test_paper.txt",
        file_hash="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef12345678",
        uri="sepolia://test_paper.txt",
        tx_hash="deadbeefcafe0000" * 4,
        block_number=7654321,
        gas_used=42000,
        owner="0xDeadBeef00000000000000000000000000001234",
        timestamp=1750000000,
        status="success",
        contract_address="0xContractAddress0000000000000000000000001",
        explorer_tx_url="https://sepolia.etherscan.io/tx/",
    )
    if with_ipfs:
        rec.ipfs_cid = "mock-deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbe"
        rec.ipfs_uri = f"ipfs://{rec.ipfs_cid}"
        rec.ipfs_gateway_url = f"https://ipfs.io/ipfs/{rec.ipfs_cid}"
        rec.ipfs_provider = "mock-ipfs"
        rec.ipfs_uploaded_at = "2026-06-22T10:00:00Z"
        rec.ipfs_sha256 = rec.file_hash
    return rec


def _mock_client(tmp: Path):
    """Return a MockIPFSClient backed by an isolated temp storage dir."""
    from proof_client.ipfs_client import MockIPFSClient
    return MockIPFSClient(storage_dir=tmp / "mock_ipfs_storage")


# ══════════════════════════════════════════════════════════════════
# 1. config.py — IPFS settings
# ══════════════════════════════════════════════════════════════════

def test_config():
    section("config.py — IPFS settings")
    try:
        from proof_client import config

        assert hasattr(config, "IPFS_PROVIDER")
        ok("IPFS_PROVIDER defined", config.IPFS_PROVIDER)

        assert hasattr(config, "IPFS_GATEWAY_URL")
        assert config.IPFS_GATEWAY_URL.startswith("http")
        ok("IPFS_GATEWAY_URL defined", config.IPFS_GATEWAY_URL)

        assert hasattr(config, "PINATA_JWT")
        ok("PINATA_JWT defined")

        assert hasattr(config, "PINATA_API_URL")
        ok("PINATA_API_URL defined", config.PINATA_API_URL)

        assert config.MOCK_IPFS_DIR.exists()
        ok("MOCK_IPFS_DIR exists on disk", config.MOCK_IPFS_DIR.name)

    except Exception as e:
        fail("config", str(e))


# ══════════════════════════════════════════════════════════════════
# 2. ipfs_client.py — formatting helpers
# ══════════════════════════════════════════════════════════════════

def test_helpers():
    section("ipfs_client.py — CID / URI / gateway helpers")
    try:
        from proof_client.ipfs_client import (
            is_valid_cid,
            format_ipfs_uri,
            parse_cid_from_uri,
            gateway_url,
            gateway_urls,
        )

        # 1) Valid CIDs
        assert is_valid_cid("mock-abc123")
        ok("is_valid_cid accepts mock CID")

        assert is_valid_cid("bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi")
        ok("is_valid_cid accepts CIDv1 (bafy...)")

        assert is_valid_cid("Qm" + "a" * 44)
        ok("is_valid_cid accepts CIDv0 (Qm...)")

        # 2) Invalid CIDs
        assert not is_valid_cid("")
        assert not is_valid_cid("not a cid!")
        assert not is_valid_cid("Qmtooshort")
        ok("is_valid_cid rejects malformed CIDs")

        # 3) format_ipfs_uri
        assert format_ipfs_uri("bafyXYZ") == "ipfs://bafyXYZ"
        ok("format_ipfs_uri builds ipfs:// URI")

        try:
            format_ipfs_uri("")
            fail("format_ipfs_uri empty", "should have raised")
        except ValueError:
            ok("format_ipfs_uri rejects empty CID")

        # 4) parse_cid_from_uri (round-trip + passthrough)
        assert parse_cid_from_uri("ipfs://bafyXYZ") == "bafyXYZ"
        assert parse_cid_from_uri("bafyXYZ") == "bafyXYZ"
        ok("parse_cid_from_uri strips ipfs:// prefix")

        # 5) gateway_url uses configured gateway by default
        url = gateway_url("bafyXYZ")
        assert url.endswith("/bafyXYZ")
        assert url.startswith("http")
        ok("gateway_url builds browsable URL", url)

        # 6) gateway_url honours an explicit gateway and avoids double slashes
        url2 = gateway_url("bafyXYZ", "https://example.com/ipfs/")
        assert url2 == "https://example.com/ipfs/bafyXYZ"
        ok("gateway_url normalises trailing slash")

        # 7) gateway_urls returns multiple distinct gateways
        urls = gateway_urls("bafyXYZ")
        assert len(urls) >= 2
        assert all(u.endswith("/bafyXYZ") for u in urls)
        assert len(set(urls)) == len(urls)
        ok("gateway_urls returns multiple gateways", f"{len(urls)} URLs")

    except Exception as e:
        fail("helpers", str(e))


# ══════════════════════════════════════════════════════════════════
# 3. MockIPFSClient — upload / download / hash invariance
# ══════════════════════════════════════════════════════════════════

def test_mock_client():
    section("ipfs_client.py — MockIPFSClient")
    try:
        from proof_client.ipfs_client import (
            IPFSUploadResult,
            is_valid_cid,
            parse_cid_from_uri,
        )
        from proof_client.hash_file import sha256_hash

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            client = _mock_client(tmp)

            src = tmp / "work.txt"
            src.write_text("hello blockchain world", encoding="utf-8")
            original_hash = sha256_hash(src)

            # 1) upload returns an IPFSUploadResult
            result = client.upload_file(src)
            assert isinstance(result, IPFSUploadResult)
            ok("upload_file returns IPFSUploadResult")

            # 2) CID is well-formed
            assert is_valid_cid(result.cid)
            ok("upload produces a valid CID", result.cid)

            # 3) URI is ipfs://<cid>
            assert result.uri == f"ipfs://{result.cid}"
            ok("upload result URI is ipfs://<cid>")

            # 4) gateway URL points at the CID
            assert result.gateway_url.endswith(result.cid)
            ok("upload result gateway URL ends with CID")

            # 5) provider label
            assert result.provider == "mock-ipfs"
            ok("upload result provider is mock-ipfs")

            # 6) uploaded_at is a UTC timestamp
            assert result.uploaded_at_utc.endswith("Z")
            ok("upload result has UTC timestamp", result.uploaded_at_utc)

            # 7) result file_sha256 == original hash (upload does not mutate)
            assert result.file_sha256 == original_hash
            ok("upload does not change SHA-256")

            # 8) content addressing: same content → same CID
            src2 = tmp / "work_copy.txt"
            src2.write_text("hello blockchain world", encoding="utf-8")
            result2 = client.upload_file(src2)
            assert result2.cid == result.cid
            ok("identical content yields identical CID (content addressing)")

            # 9) different content → different CID
            src3 = tmp / "other.txt"
            src3.write_text("different content", encoding="utf-8")
            result3 = client.upload_file(src3)
            assert result3.cid != result.cid
            ok("different content yields different CID")

            # 10) download retrieves the file
            out = tmp / "downloaded.txt"
            returned = client.download_file(result.cid, out)
            assert returned.exists()
            ok("download_file writes a file")

            # 11) downloaded content matches the original bytes
            assert out.read_text(encoding="utf-8") == "hello blockchain world"
            ok("downloaded content matches original")

            # 12) downloaded file SHA-256 matches original hash
            assert sha256_hash(out) == original_hash
            ok("downloaded file SHA-256 matches original")

            # 13) download accepts an ipfs:// URI too
            out2 = tmp / "downloaded2.txt"
            client.download_file(result.uri, out2)
            assert sha256_hash(out2) == original_hash
            ok("download_file accepts ipfs:// URI")

            # 14) unknown CID raises FileNotFoundError
            try:
                client.download_file("mock-nonexistentcid", tmp / "x.txt")
                fail("download unknown CID", "should have raised")
            except FileNotFoundError:
                ok("download_file raises on unknown CID")

            # 15) upload of a missing file raises FileNotFoundError
            try:
                client.upload_file(tmp / "does_not_exist.txt")
                fail("upload missing file", "should have raised")
            except FileNotFoundError:
                ok("upload_file raises on missing file")

    except Exception as e:
        fail("mock_client", str(e))


# ══════════════════════════════════════════════════════════════════
# 4. get_client factory
# ══════════════════════════════════════════════════════════════════

def test_get_client():
    section("ipfs_client.py — get_client factory")
    try:
        from proof_client.ipfs_client import (
            get_client,
            MockIPFSClient,
            PinataIPFSClient,
        )

        # 1) mock provider
        assert isinstance(get_client("mock"), MockIPFSClient)
        ok("get_client('mock') → MockIPFSClient")

        # 2) mock-ipfs alias
        assert isinstance(get_client("mock-ipfs"), MockIPFSClient)
        ok("get_client('mock-ipfs') → MockIPFSClient")

        # 3) pinata provider
        assert isinstance(get_client("pinata"), PinataIPFSClient)
        ok("get_client('pinata') → PinataIPFSClient")

        # 4) case-insensitive
        assert isinstance(get_client("MOCK"), MockIPFSClient)
        ok("get_client is case-insensitive")

        # 5) unknown provider raises ValueError
        try:
            get_client("nonsense")
            fail("get_client unknown", "should have raised")
        except ValueError:
            ok("get_client raises on unknown provider")

    except Exception as e:
        fail("get_client", str(e))


# ══════════════════════════════════════════════════════════════════
# 5. PinataIPFSClient — missing JWT error
# ══════════════════════════════════════════════════════════════════

def test_pinata_missing_jwt():
    section("ipfs_client.py — Pinata missing-key handling")
    try:
        from proof_client.ipfs_client import PinataIPFSClient

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "f.txt"
            src.write_text("x", encoding="utf-8")

            # 1) Empty JWT → clear RuntimeError on upload
            client = PinataIPFSClient(jwt="")
            try:
                client.upload_file(src)
                fail("pinata empty JWT", "should have raised")
            except RuntimeError as e:
                assert "PINATA_JWT" in str(e)
                ok("PinataIPFSClient raises clear error when JWT missing")

            # 2) Placeholder JWT is treated as missing
            client2 = PinataIPFSClient(jwt="your_pinata_jwt_here")
            try:
                client2.upload_file(src)
                fail("pinata placeholder JWT", "should have raised")
            except RuntimeError:
                ok("PinataIPFSClient rejects placeholder JWT")

            # 3) provider label
            assert client.provider == "pinata"
            ok("PinataIPFSClient.provider == 'pinata'")

    except Exception as e:
        fail("pinata_missing_jwt", str(e))


# ══════════════════════════════════════════════════════════════════
# 6. EvidenceRecord — IPFS fields
# ══════════════════════════════════════════════════════════════════

def test_evidence_fields():
    section("evidence_schema.py — IPFS fields")
    try:
        from proof_client.evidence_schema import EvidenceRecord

        # 1) Defaults are empty and has_ipfs is False
        plain = _make_record(with_ipfs=False)
        assert plain.ipfs_cid == ""
        assert plain.has_ipfs is False
        ok("IPFS fields default to empty; has_ipfs False")

        # 2) Populated record reports has_ipfs True
        rec = _make_record(with_ipfs=True)
        assert rec.has_ipfs is True
        ok("has_ipfs True when CID present")

        # 3) to_dict includes IPFS fields
        d = rec.to_dict()
        for key in (
            "ipfs_cid", "ipfs_uri", "ipfs_gateway_url",
            "ipfs_provider", "ipfs_uploaded_at", "ipfs_sha256",
        ):
            assert key in d, f"missing {key}"
        ok("to_dict serialises all 6 IPFS fields")

        # 4) Round-trip via from_dict preserves IPFS fields
        rec2 = EvidenceRecord.from_dict(d)
        assert rec2.ipfs_cid == rec.ipfs_cid
        assert rec2.ipfs_uri == rec.ipfs_uri
        assert rec2.ipfs_provider == rec.ipfs_provider
        ok("from_dict round-trips IPFS fields")

        # 5) Backward compatibility: old JSON without IPFS keys still loads
        legacy = {
            "file_name": "old.txt",
            "file_hash": "0x" + "a" * 60,
            "uri": "sepolia://old.txt",
        }
        legacy_rec = EvidenceRecord.from_dict(legacy)
        assert legacy_rec.ipfs_cid == ""
        assert legacy_rec.has_ipfs is False
        ok("from_dict is backward compatible with pre-Stage-7 JSON")

        # 6) JSON serialisation round-trip
        text = json.dumps(rec.to_dict())
        restored = EvidenceRecord.from_dict(json.loads(text))
        assert restored.ipfs_cid == rec.ipfs_cid
        ok("JSON serialise/deserialise preserves IPFS CID")

    except Exception as e:
        fail("evidence_fields", str(e))


# ══════════════════════════════════════════════════════════════════
# 7. evidence_store + repository persistence of IPFS fields
# ══════════════════════════════════════════════════════════════════

def test_persistence():
    section("persistence — JSON store + SQLite repo")
    try:
        from proof_client.evidence_store import save_evidence, load_evidence
        from proof_client import evidence_repository as repo
        from proof_client.config import DB_PATH

        rec = _make_record(with_ipfs=True)
        rec.file_hash = "0x" + "7" * 60  # unique key for this test

        # 1) JSON store round-trips IPFS fields
        path = save_evidence(rec)
        loaded = load_evidence(rec.file_hash)
        assert loaded is not None
        assert loaded.ipfs_cid == rec.ipfs_cid
        ok("evidence JSON store preserves IPFS CID")
        path.unlink(missing_ok=True)

        # 2) SQLite insert + read-back preserves IPFS fields
        rowid = repo.insert(rec)
        assert rowid > 0
        found = repo.find_by_hash(rec.file_hash)
        assert found is not None
        assert found.ipfs_cid == rec.ipfs_cid
        assert found.ipfs_provider == rec.ipfs_provider
        ok("SQLite repo persists IPFS fields", f"cid={found.ipfs_cid[:14]}...")

        if DB_PATH.exists():
            DB_PATH.unlink()
        ok("Cleanup test database")

    except Exception as e:
        fail("persistence", str(e))


# ══════════════════════════════════════════════════════════════════
# 8. register_file — argument parsing
# ══════════════════════════════════════════════════════════════════

def test_register_args():
    section("register_file.py — --upload-ipfs argument logic")
    try:
        from proof_client.register_file import _parse_args

        # 1) Plain registration: no IPFS
        a = _parse_args(["works/x.txt"])
        assert a.file_path == "works/x.txt"
        assert a.upload_ipfs is False
        assert a.uri is None
        ok("plain args: upload_ipfs defaults False")

        # 2) Positional URI still supported
        b = _parse_args(["works/x.txt", "custom://uri"])
        assert b.uri == "custom://uri"
        assert b.upload_ipfs is False
        ok("positional URI preserved (backward compatible)")

        # 3) --upload-ipfs flag sets the flag
        c = _parse_args(["works/x.txt", "--upload-ipfs"])
        assert c.upload_ipfs is True
        ok("--upload-ipfs sets upload_ipfs True")

        # 4) --ipfs-provider captured
        d = _parse_args(["works/x.txt", "--upload-ipfs", "--ipfs-provider", "pinata"])
        assert d.upload_ipfs is True
        assert d.ipfs_provider == "pinata"
        ok("--ipfs-provider captured", d.ipfs_provider)

    except Exception as e:
        fail("register_args", str(e))


# ══════════════════════════════════════════════════════════════════
# 9. report_template + certificate IPFS section
# ══════════════════════════════════════════════════════════════════

def test_certificate_ipfs():
    section("report_template.py — IPFS in certificate")
    try:
        from proof_client.report_template import (
            build_certificate_data,
            build_markdown_certificate,
        )

        # 1) certificate data carries IPFS keys
        rec = _make_record(with_ipfs=True)
        d = build_certificate_data(rec)
        assert d["has_ipfs"] is True
        assert d["ipfs_cid"] == rec.ipfs_cid
        ok("build_certificate_data includes IPFS fields")

        # 2) Markdown certificate shows the CID
        md = build_markdown_certificate(rec)
        assert rec.ipfs_cid in md
        assert "IPFS" in md
        ok("Markdown certificate shows IPFS CID")

        # 3) Markdown still has all earlier sections (1..8 present)
        for i in range(1, 9):
            assert f"{i}." in md, f"section {i} missing"
        ok("certificate retains sections 1-8 plus IPFS")

        # 4) Record without IPFS shows 'Not available'
        plain = _make_record(with_ipfs=False)
        d2 = build_certificate_data(plain)
        assert d2["ipfs_cid"] == "Not available"
        md2 = build_markdown_certificate(plain)
        assert "Not available" in md2
        ok("certificate shows 'Not available' without IPFS")

    except Exception as e:
        fail("certificate_ipfs", str(e))


# ══════════════════════════════════════════════════════════════════
# 10. pdf_report — IPFS section renders
# ══════════════════════════════════════════════════════════════════

def test_pdf_ipfs():
    section("pdf_report.py — IPFS section renders")
    try:
        from proof_client.pdf_report import generate_pdf

        rec = _make_record(with_ipfs=True)
        pdf_path = generate_pdf(rec)
        assert pdf_path.exists()
        with open(pdf_path, "rb") as f:
            assert f.read(4) == b"%PDF"
        ok("PDF with IPFS section generates valid file", f"{pdf_path.stat().st_size} bytes")
        pdf_path.unlink(missing_ok=True)

        # Record without IPFS still generates a valid PDF
        plain = _make_record(with_ipfs=False)
        pdf_path2 = generate_pdf(plain)
        assert pdf_path2.exists()
        ok("PDF without IPFS still generates")
        pdf_path2.unlink(missing_ok=True)

    except Exception as e:
        fail("pdf_ipfs", str(e))


# ══════════════════════════════════════════════════════════════════
# 11. verification_guide — Step 4 IPFS
# ══════════════════════════════════════════════════════════════════

def test_guide_ipfs():
    section("verification_guide.py — Step 4 IPFS")
    try:
        from proof_client.verification_guide import (
            build_verification_guide,
            build_verification_commands,
        )

        # 1) Guide with IPFS includes Step 4 and CID
        rec = _make_record(with_ipfs=True)
        guide = build_verification_guide(rec)
        assert "Step 4" in guide
        assert "IPFS" in guide
        assert rec.ipfs_cid in guide
        ok("guide includes Step 4 with CID")

        # 2) Guide includes curl + shasum verification commands
        assert "curl" in guide
        assert "shasum" in guide
        ok("guide includes curl + shasum IPFS instructions")

        # 3) Guide explains CID vs SHA-256 distinction
        assert "related but" in guide and "identical" in guide
        ok("guide explains CID vs SHA-256 distinction")

        # 4) Guide without IPFS still includes a Step 4 (marked N/A)
        plain = _make_record(with_ipfs=False)
        guide2 = build_verification_guide(plain)
        assert "Step 4" in guide2
        assert "not applicable" in guide2.lower()
        ok("guide marks Step 4 N/A when no CID")

        # 5) Commands file includes verify_ipfs when CID present
        cmds = build_verification_commands(rec)
        assert "verify_ipfs" in cmds
        assert rec.ipfs_cid in cmds
        ok("commands file includes verify_ipfs command")

        # 6) Commands file without IPFS notes no CID
        cmds2 = build_verification_commands(plain)
        assert "no CID" in cmds2.lower() or "no cid" in cmds2.lower()
        ok("commands file notes absence of CID")

    except Exception as e:
        fail("guide_ipfs", str(e))


# ══════════════════════════════════════════════════════════════════
# 12. package_exporter — ipfs/ directory + manifest
# ══════════════════════════════════════════════════════════════════

def test_package_ipfs():
    section("package_exporter.py — ipfs/ directory")
    try:
        from proof_client.package_exporter import build_package
        from proof_client.evidence_store import save_evidence
        from proof_client.config import DB_PATH

        rec = _make_record(with_ipfs=True)
        rec.file_hash = "0x" + "c" * 60  # unique
        ev_path = save_evidence(rec)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            pkg_dir = build_package(rec, output_dir)

            # 1) ipfs/ directory created
            ipfs_dir = pkg_dir / "ipfs"
            assert ipfs_dir.exists()
            ok("ipfs/ directory created in package")

            # 2) ipfs_metadata.json present and valid
            meta_path = ipfs_dir / "ipfs_metadata.json"
            assert meta_path.exists()
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            assert meta["ipfs_cid"] == rec.ipfs_cid
            assert meta["ipfs_uri"] == rec.ipfs_uri
            assert isinstance(meta["gateway_urls"], list) and meta["gateway_urls"]
            ok("ipfs_metadata.json valid with CID + gateways")

            # 3) ipfs_gateway_links.txt present and lists the CID
            links_path = ipfs_dir / "ipfs_gateway_links.txt"
            assert links_path.exists()
            assert rec.ipfs_cid in links_path.read_text(encoding="utf-8")
            ok("ipfs_gateway_links.txt lists the CID")

            # 4) manifest includes ipfs/ files
            manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
            paths = {e["path"].replace("\\", "/") for e in manifest["files"]}
            assert any(p.startswith("ipfs/") for p in paths)
            ok("manifest includes ipfs/ files")

            # 5) README mentions the CID
            readme = (pkg_dir / "README.md").read_text(encoding="utf-8")
            assert rec.ipfs_cid in readme
            ok("package README references the CID")

        ev_path.unlink(missing_ok=True)
        if DB_PATH.exists():
            DB_PATH.unlink()
        ok("Cleanup package IPFS test")

    except Exception as e:
        fail("package_ipfs", str(e))


def test_package_no_ipfs():
    section("package_exporter.py — no ipfs/ when CID absent")
    try:
        from proof_client.package_exporter import build_package
        from proof_client.evidence_store import save_evidence
        from proof_client.config import DB_PATH

        rec = _make_record(with_ipfs=False)
        rec.file_hash = "0x" + "d" * 60
        ev_path = save_evidence(rec)

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = build_package(rec, Path(tmpdir))
            assert not (pkg_dir / "ipfs").exists()
            ok("no ipfs/ directory when record has no CID")

        ev_path.unlink(missing_ok=True)
        if DB_PATH.exists():
            DB_PATH.unlink()
        ok("Cleanup no-IPFS package test")

    except Exception as e:
        fail("package_no_ipfs", str(e))


# ══════════════════════════════════════════════════════════════════
# 13. verify_ipfs — success + failure
# ══════════════════════════════════════════════════════════════════

def test_verify_ipfs():
    section("verify_ipfs.py — success + tamper detection")
    try:
        from proof_client.ipfs_client import MockIPFSClient
        from proof_client.verify_ipfs import verify_ipfs, verify_ipfs_by_hash
        from proof_client.hash_file import sha256_hash
        from proof_client.config import MOCK_IPFS_DIR
        from proof_client.evidence_store import save_evidence

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Use the real configured MOCK_IPFS_DIR so verify_ipfs (which builds
            # its own default client) can find the content.
            client = MockIPFSClient()

            src = tmp / "art.txt"
            src.write_text("a unique creative work for stage 7", encoding="utf-8")
            file_hash = sha256_hash(src)
            up = client.upload_file(src)

            # 1) Matching hash → match True
            result = verify_ipfs(up.cid, file_hash, provider="mock")
            assert result["match"] is True
            assert result["actual_hash"] == file_hash
            ok("verify_ipfs succeeds for correct hash")

            # 2) Tampered/expected-wrong hash → match False
            wrong = "0x" + "0" * 64
            result2 = verify_ipfs(up.cid, wrong, provider="mock")
            assert result2["match"] is False
            ok("verify_ipfs detects hash mismatch")

            # 3) ipfs:// URI accepted as CID
            result3 = verify_ipfs(up.uri, file_hash, provider="mock")
            assert result3["match"] is True
            ok("verify_ipfs accepts ipfs:// URI")

            # 4) verify_ipfs_by_hash via stored evidence
            rec = _make_record(with_ipfs=True)
            rec.file_hash = file_hash
            rec.ipfs_cid = up.cid
            rec.ipfs_uri = up.uri
            rec.ipfs_provider = "mock-ipfs"
            ev_path = save_evidence(rec)

            result4 = verify_ipfs_by_hash(file_hash)
            assert result4 is not None and result4["match"] is True
            ok("verify_ipfs_by_hash matches stored evidence")

            # 5) verify_ipfs_by_hash returns None for unknown hash
            assert verify_ipfs_by_hash("0x" + "e" * 60) is None
            ok("verify_ipfs_by_hash returns None for unknown hash")

            ev_path.unlink(missing_ok=True)

            # 6) Unknown CID raises FileNotFoundError
            try:
                verify_ipfs("mock-doesnotexist0000", file_hash, provider="mock")
                fail("verify unknown CID", "should have raised")
            except FileNotFoundError:
                ok("verify_ipfs raises on unknown CID")

            # Cleanup uploaded mock content
            (MOCK_IPFS_DIR / up.cid).unlink(missing_ok=True)

    except Exception as e:
        fail("verify_ipfs", str(e))


# ══════════════════════════════════════════════════════════════════
# 14. ipfs_upload / ipfs_download CLI functions
# ══════════════════════════════════════════════════════════════════

def test_cli_functions():
    section("ipfs_upload / ipfs_download — function level")
    try:
        from proof_client.ipfs_upload import upload_to_ipfs
        from proof_client.ipfs_download import download_from_ipfs
        from proof_client.hash_file import sha256_hash
        from proof_client.config import MOCK_IPFS_DIR

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            src = tmp / "cli_work.txt"
            src.write_text("cli round trip test", encoding="utf-8")
            original = sha256_hash(src)

            # 1) upload_to_ipfs returns a result with a CID
            result = upload_to_ipfs(str(src), provider="mock")
            assert result.cid
            ok("upload_to_ipfs returns CID", result.cid)

            # 2) download_from_ipfs retrieves identical content
            out = tmp / "cli_out.txt"
            download_from_ipfs(result.cid, out, provider="mock")
            assert sha256_hash(out) == original
            ok("download_from_ipfs round-trips identical content")

            # Cleanup mock store
            (MOCK_IPFS_DIR / result.cid).unlink(missing_ok=True)

    except Exception as e:
        fail("cli_functions", str(e))


# ══════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════

def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║          proof_client Stage 7 Test Suite                 ║")
    print("║  IPFS · CID · Mock Client · verify_ipfs · Package        ║")
    print("╚══════════════════════════════════════════════════════════╝")

    test_config()
    test_helpers()
    test_mock_client()
    test_get_client()
    test_pinata_missing_jwt()
    test_evidence_fields()
    test_persistence()
    test_register_args()
    test_certificate_ipfs()
    test_pdf_ipfs()
    test_guide_ipfs()
    test_package_ipfs()
    test_package_no_ipfs()
    test_verify_ipfs()
    test_cli_functions()

    total = _passed + _failed
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print(f"║  📊 Results: {_passed}/{total} passed, {_failed} failed{' ' * (24 - len(str(_passed)) - len(str(total)) - len(str(_failed)))}║")
    print("╚══════════════════════════════════════════════════════════╝")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
