"""
test_stage6.py — Stage 6 test suite

Tests PDF generation, ZIP evidence packages, manifest integrity,
verification guides, and the export/verify CLIs.

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m proof_client.test_stage6
"""

import json
import os
import sys
import shutil
import tempfile
import zipfile
from pathlib import Path

# ══════════════════════════════════════════════════════════════════
# Test helpers (same style as test_all.py)
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
    print(f"  📦 {title}")
    print(f"{'━'*60}")


# ── Shared fixture ─────────────────────────────────────────────────

def _make_record():
    """Return a fully-populated EvidenceRecord for testing."""
    from proof_client.evidence_schema import EvidenceRecord
    return EvidenceRecord(
        file_name="test_paper.txt",
        file_hash="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef12345678",
        uri="sepolia://test_paper.txt",
        tx_hash="deadbeefcafe0000" * 4,
        block_number=7654321,
        gas_used=42000,
        owner="0xDeadBeef00000000000000000000000000001234",
        timestamp=1750000000,
        status="success",
        network="Ethereum Sepolia",
        chain_id=11155111,
        contract_address="0xContractAddress0000000000000000000000001",
        explorer_tx_url="https://sepolia.etherscan.io/tx/",
    )


# ══════════════════════════════════════════════════════════════════
# 1. report_template.py
# ══════════════════════════════════════════════════════════════════

def test_report_template():
    section("report_template.py")
    try:
        from proof_client.report_template import (
            build_certificate_data,
            build_markdown_certificate,
            LIMITATIONS_TEXT,
            DECLARATION_TEXT,
        )

        record = _make_record()

        # 1) build_certificate_data returns a dict
        data = build_certificate_data(record)
        assert isinstance(data, dict)
        ok("build_certificate_data returns dict")

        # 2) certificate_id derived from hash
        assert data["certificate_id"].startswith("POE-")
        assert "ABCDEF12" in data["certificate_id"]
        ok("certificate_id format", data["certificate_id"])

        # 3) generated_at_utc present and UTC-labelled
        assert "UTC" in data["generated_at_utc"]
        ok("generated_at_utc has UTC label")

        # 4) file_name preserved
        assert data["file_name"] == "test_paper.txt"
        ok("file_name preserved")

        # 5) file_hash preserved
        assert data["file_hash"] == record.file_hash
        ok("file_hash preserved")

        # 6) tx_hash gets 0x prefix
        assert data["tx_hash"].startswith("0x")
        ok("tx_hash prefixed with 0x")

        # 7) manifest_hash defaults to N/A
        assert data["package_manifest_hash"] == "N/A"
        ok("package_manifest_hash defaults to N/A")

        # 8) manifest_hash accepted when provided
        data2 = build_certificate_data(record, manifest_hash="abc123")
        assert data2["package_manifest_hash"] == "abc123"
        ok("package_manifest_hash populated from argument")

        # 9) limitations text is present and correct
        assert "SHA-256" in LIMITATIONS_TEXT
        assert "legal authorship" in LIMITATIONS_TEXT
        assert "copyright" in LIMITATIONS_TEXT
        ok("LIMITATIONS_TEXT contains required phrases")

        # 10) declaration text present
        assert "immutable" in DECLARATION_TEXT
        ok("DECLARATION_TEXT present and correct")

        # 11) build_markdown_certificate returns a string
        md = build_markdown_certificate(record)
        assert isinstance(md, str)
        ok("build_markdown_certificate returns string")

        # 12) Markdown contains all 8 section headers
        for i in range(1, 9):
            assert f"{i}." in md, f"Section {i} missing"
        ok("All 8 sections present in Markdown")

        # 13) File hash appears in Markdown
        assert record.file_hash in md
        ok("file_hash in Markdown certificate")

        # 14) Limitations text appears in Markdown
        assert "legal authorship" in md
        ok("Limitations section in Markdown")

        # 15) Declaration appears in Markdown
        assert "immutable" in md
        ok("Declaration section in Markdown")

    except Exception as e:
        fail("report_template", str(e))


# ══════════════════════════════════════════════════════════════════
# 2. pdf_report.py
# ══════════════════════════════════════════════════════════════════

def test_pdf_report():
    section("pdf_report.py")
    try:
        from proof_client.pdf_report import generate_pdf
        from proof_client.config import REPORTS_DIR

        record = _make_record()
        short = record.file_hash.replace("0x", "")[:8]

        # 1) PDF file is generated
        pdf_path = generate_pdf(record)
        assert pdf_path is not None
        ok("generate_pdf returns a path")

        # 2) File exists on disk
        assert pdf_path.exists()
        ok("PDF file exists on disk", str(pdf_path.name))

        # 3) File is non-empty
        size = pdf_path.stat().st_size
        assert size > 1000, f"PDF too small: {size} bytes"
        ok("PDF file is non-empty", f"{size} bytes")

        # 4) File starts with PDF magic bytes
        with open(pdf_path, "rb") as f:
            magic = f.read(4)
        assert magic == b"%PDF", f"Not a PDF: {magic}"
        ok("PDF magic bytes correct")

        # 5) Filename follows convention
        assert pdf_path.name == f"proof_report_{short}.pdf"
        ok("PDF filename correct", pdf_path.name)

        # 6) Saved to REPORTS_DIR
        assert pdf_path.parent == REPORTS_DIR
        ok("PDF saved in REPORTS_DIR")

        # 7) manifest_hash is passed through (does not raise)
        pdf_path2 = generate_pdf(record, manifest_hash="cafecafe1234")
        assert pdf_path2.exists()
        ok("generate_pdf with manifest_hash succeeds")

        # Cleanup
        pdf_path.unlink(missing_ok=True)
        ok("Cleanup PDF test file")

    except Exception as e:
        fail("pdf_report", str(e))


# ══════════════════════════════════════════════════════════════════
# 3. manifest.py
# ══════════════════════════════════════════════════════════════════

def test_manifest():
    section("manifest.py")
    try:
        from proof_client.manifest import (
            sha256_file,
            sha256_bytes,
            build_manifest,
            write_manifest,
            verify_manifest,
            verify_manifest_in_zip,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)

            # Create a few test files
            (pkg_dir / "file_a.txt").write_text("hello world", encoding="utf-8")
            (pkg_dir / "subdir").mkdir()
            (pkg_dir / "subdir" / "file_b.txt").write_text("blockchain", encoding="utf-8")

            # 1) sha256_file produces a 64-char hex string
            h = sha256_file(pkg_dir / "file_a.txt")
            assert len(h) == 64
            ok("sha256_file produces 64-char hex", h[:16] + "...")

            # 2) sha256_bytes is consistent
            h2 = sha256_bytes(b"hello world")
            assert h == h2
            ok("sha256_bytes matches sha256_file for same content")

            # 3) build_manifest returns correct structure
            m = build_manifest(pkg_dir)
            assert m["package_version"] == "1.0"
            assert m["package_type"] == "ProofOfExistenceEvidencePackage"
            assert isinstance(m["files"], list)
            ok("build_manifest structure correct")

            # 4) All files included (manifest.json excluded)
            paths_in_manifest = {e["path"] for e in m["files"]}
            assert "file_a.txt" in paths_in_manifest
            assert "subdir/file_b.txt" in paths_in_manifest or "subdir\\file_b.txt" in paths_in_manifest
            ok("build_manifest includes all files", f"{len(m['files'])} entries")

            # 5) manifest.json excluded from its own listing
            assert not any("manifest.json" in e["path"] for e in m["files"])
            ok("manifest.json excluded from file list")

            # 6) write_manifest writes file and returns hash
            mpath, mhash = write_manifest(pkg_dir)
            assert mpath.exists()
            assert len(mhash) == 64
            ok("write_manifest creates manifest.json", f"hash={mhash[:12]}...")

            # 7) manifest.json is valid JSON
            content = json.loads(mpath.read_text(encoding="utf-8"))
            assert "files" in content
            ok("manifest.json is valid JSON")

            # 8) verify_manifest passes for untampered package
            ok_flag, errors = verify_manifest(pkg_dir)
            assert ok_flag, f"Verify failed: {errors}"
            ok("verify_manifest passes for clean package")

            # 9) verify_manifest detects tampered file
            (pkg_dir / "file_a.txt").write_text("tampered!", encoding="utf-8")
            ok_flag2, errors2 = verify_manifest(pkg_dir)
            assert not ok_flag2
            assert any("file_a.txt" in e for e in errors2)
            ok("verify_manifest detects file tampering", errors2[0])

            # 10) verify_manifest detects missing file
            (pkg_dir / "subdir" / "file_b.txt").unlink()
            ok_flag3, errors3 = verify_manifest(pkg_dir)
            assert not ok_flag3
            ok("verify_manifest detects missing file")

            # 11) verify_manifest_in_zip works on a ZIP
            # Re-create clean state
            (pkg_dir / "file_a.txt").write_text("hello world", encoding="utf-8")
            (pkg_dir / "subdir" / "file_b.txt").write_text("blockchain", encoding="utf-8")
            write_manifest(pkg_dir)

            zip_path = Path(tmpdir) / "test_package.zip"
            import zipfile as zf_mod
            with zf_mod.ZipFile(zip_path, "w") as zf:
                for f in sorted(pkg_dir.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(pkg_dir))

            ok_flag4, errors4 = verify_manifest_in_zip(zip_path)
            assert ok_flag4, f"ZIP verify failed: {errors4}"
            ok("verify_manifest_in_zip passes for clean ZIP")

            # 12) verify_manifest_in_zip on non-existent file
            ok_flag5, errors5 = verify_manifest_in_zip(Path("/nonexistent/pkg.zip"))
            assert not ok_flag5
            ok("verify_manifest_in_zip handles missing ZIP")

    except Exception as e:
        fail("manifest", str(e))


# ══════════════════════════════════════════════════════════════════
# 4. verification_guide.py
# ══════════════════════════════════════════════════════════════════

def test_verification_guide():
    section("verification_guide.py")
    try:
        from proof_client.verification_guide import (
            build_verification_guide,
            build_verification_commands,
            write_verification_guide,
        )

        record = _make_record()

        # 1) build_verification_guide returns string
        guide = build_verification_guide(record)
        assert isinstance(guide, str)
        ok("build_verification_guide returns string")

        # 2) Guide contains file name
        assert record.file_name in guide
        ok("Guide contains file name")

        # 3) Guide contains file hash
        assert record.file_hash in guide
        ok("Guide contains file hash")

        # 4) Guide contains contract address
        assert record.contract_address in guide
        ok("Guide contains contract address")

        # 5) Guide has shasum command
        assert "shasum" in guide
        ok("Guide includes shasum verification command")

        # 6) Guide mentions block explorer
        assert "etherscan" in guide.lower() or "explorer" in guide.lower()
        ok("Guide references block explorer")

        # 7) Guide includes Python/web3 verification code
        assert "web3" in guide or "Web3" in guide
        ok("Guide includes web3 verification code")

        # 8) Guide includes ethers.js option
        assert "ethers" in guide
        ok("Guide includes ethers.js option")

        # 9) Guide mentions what it does NOT prove (legal authorship)
        assert "legal" in guide.lower()
        ok("Guide clarifies legal limitations")

        # 10) build_verification_commands returns string
        cmds = build_verification_commands(record)
        assert isinstance(cmds, str)
        ok("build_verification_commands returns string")

        # 11) Commands contain shasum
        assert "shasum" in cmds
        ok("Commands include shasum")

        # 12) Commands contain expected hash
        assert record.file_hash in cmds
        ok("Commands include expected hash")

        # 13) write_verification_guide creates both files
        with tempfile.TemporaryDirectory() as tmpdir:
            ver_dir = Path(tmpdir) / "verification"
            guide_path, cmds_path = write_verification_guide(record, ver_dir)

            assert guide_path.exists()
            ok("verification_guide.md created")

            assert cmds_path.exists()
            ok("verification_commands.txt created")

            # 14) Files are non-empty
            assert guide_path.stat().st_size > 100
            ok("verification_guide.md is non-empty")

            assert cmds_path.stat().st_size > 50
            ok("verification_commands.txt is non-empty")

    except Exception as e:
        fail("verification_guide", str(e))


# ══════════════════════════════════════════════════════════════════
# 5. package_exporter.py
# ══════════════════════════════════════════════════════════════════

def test_package_exporter():
    section("package_exporter.py")
    try:
        from proof_client.package_exporter import build_package, zip_package, export_package
        from proof_client.evidence_store import save_evidence
        from proof_client.config import EVIDENCE_DIR, REPORTS_DIR

        record = _make_record()
        short = record.file_hash.replace("0x", "")[:8]

        # Pre-save evidence JSON so package can copy it
        ev_path = save_evidence(record)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # 1) build_package creates the directory
            pkg_dir = build_package(record, output_dir)
            assert pkg_dir.exists() and pkg_dir.is_dir()
            ok("build_package creates package directory", pkg_dir.name)

            # 2) original/ subdirectory exists
            orig_dir = pkg_dir / "original"
            assert orig_dir.exists()
            ok("original/ directory created")

            # 3) original/ contains the work file (placeholder or real)
            orig_files = list(orig_dir.iterdir())
            assert len(orig_files) == 1
            ok("original/ contains one file", orig_files[0].name)

            # 4) evidence/ subdirectory exists
            ev_dir = pkg_dir / "evidence"
            assert ev_dir.exists()
            ok("evidence/ directory created")

            # 5) evidence JSON present
            ev_json = ev_dir / f"evidence_{short}.json"
            assert ev_json.exists()
            ok("evidence JSON in package", ev_json.name)

            # 6) reports/ subdirectory exists
            rep_dir = pkg_dir / "reports"
            assert rep_dir.exists()
            ok("reports/ directory created")

            # 7) Markdown report present
            md_files = list(rep_dir.glob("*.md"))
            assert len(md_files) >= 1
            ok("Markdown report in reports/", md_files[0].name)

            # 8) PDF report present
            pdf_files = list(rep_dir.glob("*.pdf"))
            assert len(pdf_files) >= 1
            ok("PDF report in reports/", pdf_files[0].name)

            # 9) verification/ subdirectory exists
            ver_dir = pkg_dir / "verification"
            assert ver_dir.exists()
            ok("verification/ directory created")

            # 10) verification_guide.md present
            guide = ver_dir / "verification_guide.md"
            assert guide.exists()
            ok("verification_guide.md present")

            # 11) verification_commands.txt present
            cmds = ver_dir / "verification_commands.txt"
            assert cmds.exists()
            ok("verification_commands.txt present")

            # 12) manifest.json present
            mf = pkg_dir / "manifest.json"
            assert mf.exists()
            ok("manifest.json present")

            # 13) manifest.json is valid JSON with expected structure
            mdata = json.loads(mf.read_text(encoding="utf-8"))
            assert "files" in mdata
            assert mdata["package_type"] == "ProofOfExistenceEvidencePackage"
            ok("manifest.json structure valid")

            # 14) manifest contains >= 6 files
            assert len(mdata["files"]) >= 6
            ok("manifest lists >= 6 files", f"{len(mdata['files'])} entries")

            # 15) README.md present
            readme = pkg_dir / "README.md"
            assert readme.exists()
            ok("README.md present")

            # 16) README.md contains file name
            assert record.file_name in readme.read_text(encoding="utf-8")
            ok("README.md contains file name")

            # 17) zip_package creates a ZIP
            zip_path = zip_package(pkg_dir, output_dir)
            assert zip_path.exists()
            ok("zip_package creates ZIP file", zip_path.name)

            # 18) ZIP is non-empty
            assert zip_path.stat().st_size > 1000
            ok("ZIP file is non-empty", f"{zip_path.stat().st_size} bytes")

            # 19) ZIP is a valid ZIP archive
            assert zipfile.is_zipfile(str(zip_path))
            ok("ZIP file is valid archive")

            # 20) ZIP contains all required paths
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
            assert any("manifest.json" in n for n in names)
            assert any("README.md" in n for n in names)
            assert any("evidence" in n and ".json" in n for n in names)
            assert any("reports" in n and ".pdf" in n for n in names)
            assert any("verification" in n and ".md" in n for n in names)
            ok("ZIP contains all required paths")

        # Cleanup evidence file
        ev_path.unlink(missing_ok=True)
        ok("Cleanup evidence JSON")

    except Exception as e:
        fail("package_exporter", str(e))


# ══════════════════════════════════════════════════════════════════
# 6. verify_package — integrity check
# ══════════════════════════════════════════════════════════════════

def test_verify_package():
    section("verify_package — integrity check")
    try:
        from proof_client.manifest import write_manifest, verify_manifest, verify_manifest_in_zip

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "pkg"
            pkg_dir.mkdir()
            (pkg_dir / "file.txt").write_text("original content", encoding="utf-8")
            (pkg_dir / "sub").mkdir()
            (pkg_dir / "sub" / "data.json").write_text('{"ok":true}', encoding="utf-8")

            write_manifest(pkg_dir)

            # 1) Clean directory → verify passes
            ok_flag, errors = verify_manifest(pkg_dir)
            assert ok_flag, errors
            ok("verify_manifest passes for clean dir")

            # 2) Tamper a file → verify fails
            (pkg_dir / "file.txt").write_text("tampered!", encoding="utf-8")
            ok_flag2, errors2 = verify_manifest(pkg_dir)
            assert not ok_flag2
            ok("verify_manifest detects tampered file", errors2[0])

            # Restore
            (pkg_dir / "file.txt").write_text("original content", encoding="utf-8")
            write_manifest(pkg_dir)

            # 3) Delete a file → verify fails
            (pkg_dir / "sub" / "data.json").unlink()
            ok_flag3, errors3 = verify_manifest(pkg_dir)
            assert not ok_flag3
            ok("verify_manifest detects deleted file", errors3[0])

            # Restore and make ZIP
            (pkg_dir / "sub" / "data.json").write_text('{"ok":true}', encoding="utf-8")
            write_manifest(pkg_dir)

            zip_path = Path(tmpdir) / "test.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(pkg_dir.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(pkg_dir))

            # 4) ZIP verify passes for clean ZIP
            ok_flag4, errors4 = verify_manifest_in_zip(zip_path)
            assert ok_flag4, errors4
            ok("verify_manifest_in_zip passes for clean ZIP")

            # 5) Tampered ZIP → detect hash mismatch
            import zipfile as zf_mod
            tampered_zip = Path(tmpdir) / "tampered.zip"
            with zf_mod.ZipFile(zip_path, "r") as src_zf:
                with zf_mod.ZipFile(tampered_zip, "w") as dst_zf:
                    for name in src_zf.namelist():
                        if name.endswith("file.txt"):
                            dst_zf.writestr(name, b"tampered content in ZIP")
                        else:
                            dst_zf.writestr(name, src_zf.read(name))

            ok_flag5, errors5 = verify_manifest_in_zip(tampered_zip)
            assert not ok_flag5
            ok("verify_manifest_in_zip detects tampered content in ZIP", errors5[0])

    except Exception as e:
        fail("verify_package", str(e))


# ══════════════════════════════════════════════════════════════════
# 7. export_package CLI (function-level)
# ══════════════════════════════════════════════════════════════════

def test_export_package_cli():
    section("export_package CLI functions")
    try:
        from proof_client.package_exporter import export_by_hash, export_all
        from proof_client.evidence_store import save_evidence
        from proof_client.config import EVIDENCE_DIR

        record = _make_record()
        ev_path = save_evidence(record)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # 1) export_by_hash returns (pkg_dir, zip_path)
            result = export_by_hash(record.file_hash, output_dir)
            assert result is not None
            pkg_dir, zip_path = result
            ok("export_by_hash returns (pkg_dir, zip_path)")

            # 2) ZIP file created
            assert zip_path.exists()
            ok("export_by_hash ZIP exists", zip_path.name)

            # 3) export_by_hash with bad hash → None
            result2 = export_by_hash("0xnonexistent" + "0" * 54, output_dir)
            assert result2 is None
            ok("export_by_hash returns None for unknown hash")

            # 4) export_all returns a list
            results = export_all(output_dir)
            assert isinstance(results, list)
            assert len(results) >= 1
            ok("export_all returns list", f"{len(results)} package(s)")

            # 5) export_all with no evidence → empty list
            from proof_client.evidence_store import list_all_evidence
            records = list_all_evidence()
            if len(records) == 0:
                empty_results = export_all(output_dir)
                assert empty_results == []
                ok("export_all returns [] when no evidence")
            else:
                ok("export_all skipped empty-check (evidence exists)")

        # Cleanup
        ev_path.unlink(missing_ok=True)
        ok("Cleanup evidence JSON for CLI test")

    except Exception as e:
        fail("export_package_cli", str(e))


# ══════════════════════════════════════════════════════════════════
# 8. evidence_repository.find_by_id
# ══════════════════════════════════════════════════════════════════

def test_find_by_id():
    section("evidence_repository.find_by_id")
    try:
        from proof_client import evidence_repository as repo
        from proof_client.config import DB_PATH

        record = _make_record()
        record.file_hash = "0x_test_id_lookup_" + "f" * 46

        # 1) Insert and get rowid
        rowid = repo.insert(record)
        assert rowid > 0
        ok("insert returns positive rowid", str(rowid))

        # 2) find_by_id retrieves the record
        found = repo.find_by_id(rowid)
        assert found is not None
        assert found.file_name == record.file_name
        ok("find_by_id returns correct record", f"file={found.file_name}")

        # 3) find_by_id with non-existent id → None
        not_found = repo.find_by_id(99999999)
        assert not_found is None
        ok("find_by_id returns None for unknown id")

        # Cleanup
        if DB_PATH.exists():
            DB_PATH.unlink()
        ok("Cleanup test database")

    except Exception as e:
        fail("find_by_id", str(e))


# ══════════════════════════════════════════════════════════════════
# 9. config.py PACKAGES_DIR
# ══════════════════════════════════════════════════════════════════

def test_packages_dir():
    section("config.py — PACKAGES_DIR")
    try:
        from proof_client.config import PACKAGES_DIR

        # 1) PACKAGES_DIR is defined
        assert PACKAGES_DIR is not None
        ok("PACKAGES_DIR defined")

        # 2) PACKAGES_DIR is created automatically
        assert PACKAGES_DIR.exists()
        ok("PACKAGES_DIR exists on disk", str(PACKAGES_DIR))

        # 3) PACKAGES_DIR is named 'packages'
        assert PACKAGES_DIR.name == "packages"
        ok("PACKAGES_DIR is named 'packages'")

    except Exception as e:
        fail("packages_dir", str(e))


# ══════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════

def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║          proof_client Stage 6 Test Suite                 ║")
    print("║  PDF · ZIP Package · Manifest · Verification Guide       ║")
    print("╚══════════════════════════════════════════════════════════╝")

    test_packages_dir()
    test_report_template()
    test_pdf_report()
    test_manifest()
    test_verification_guide()
    test_package_exporter()
    test_verify_package()
    test_export_package_cli()
    test_find_by_id()

    total = _passed + _failed
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print(f"║  📊 Results: {_passed}/{total} passed, {_failed} failed{' ' * (24 - len(str(_passed)) - len(str(total)) - len(str(_failed)))}║")
    print("╚══════════════════════════════════════════════════════════╝")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
