"""
test_stage8.py — Stage 8 test suite (encrypted IPFS upload)

Covers AES-256-GCM + PBKDF2 crypto primitives, the encrypt/decrypt CLIs, the
EvidenceRecord encryption fields and backward compatibility, the SQLite column
migration, encrypt-then-upload to mock IPFS, register_file argument rules, the
verify_encrypted_ipfs success/failure paths, the certificate / guide / package
encrypted sections, and the security invariant that passwords/keys are never
stored.

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m proof_client.test_stage8
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

# ══════════════════════════════════════════════════════════════════
# Test helpers (same style as test_stage7.py)
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
    print(f"  🔒 {title}")
    print(f"{'━'*60}")


# ── Shared fixtures ────────────────────────────────────────────────

# Low iteration count keeps the test suite fast; production uses 600k.
_FAST_ITERS = 50_000


def _make_plaintext(tmp: Path, name: str = "secret.txt") -> Path:
    p = tmp / name
    p.write_bytes(b"Stage 8 confidential manuscript. " * 64)
    return p


def _encrypt_to(tmp: Path):
    """Encrypt a fresh plaintext and return (src, enc_path, EncryptionResult)."""
    from proof_client.crypto_utils import encrypt_file
    src = _make_plaintext(tmp)
    enc = tmp / "secret.txt.enc"
    res = encrypt_file(src, enc, "correct horse", iterations=_FAST_ITERS)
    return src, enc, res


def _make_encrypted_record(res, cid: str = "mock-stage8cidstage8cidstage8cidstage8cid00"):
    """Build an encrypted EvidenceRecord from an EncryptionResult."""
    from proof_client.evidence_schema import EvidenceRecord
    rec = EvidenceRecord(
        file_name="secret.txt",
        file_hash=res.original_sha256,
        uri=f"ipfs://{cid}",
        owner="0xDeadBeef00000000000000000000000000001234",
        contract_address="0xContractAddress0000000000000000000000001",
        explorer_tx_url="https://sepolia.etherscan.io/tx/",
    )
    rec.is_encrypted = True
    rec.encryption_algorithm = res.algorithm
    rec.encryption_kdf = res.kdf
    rec.encryption_kdf_iterations = res.kdf_iterations
    rec.encryption_salt_hex = res.salt_hex
    rec.encryption_nonce_hex = res.nonce_hex
    rec.encrypted_file_hash = res.encrypted_sha256
    rec.encrypted_file_name = "secret.txt.enc"
    rec.encrypted_ipfs_cid = cid
    rec.encrypted_ipfs_uri = f"ipfs://{cid}"
    rec.encrypted_ipfs_gateway_url = f"https://ipfs.io/ipfs/{cid}"
    rec.encrypted_ipfs_provider = "mock-ipfs"
    rec.encrypted_ipfs_uploaded_at = "2026-06-24T10:00:00Z"
    # Mirror into generic IPFS fields (register_file does the same).
    rec.ipfs_cid = cid
    rec.ipfs_uri = rec.encrypted_ipfs_uri
    rec.ipfs_gateway_url = rec.encrypted_ipfs_gateway_url
    rec.ipfs_provider = "mock-ipfs"
    rec.ipfs_sha256 = res.encrypted_sha256
    return rec


# ══════════════════════════════════════════════════════════════════
# 1. config.py — encryption settings
# ══════════════════════════════════════════════════════════════════

def test_config():
    section("config.py — encryption settings")
    try:
        from proof_client import config

        assert config.ENCRYPTION_ALGORITHM == "AES-256-GCM"
        ok("ENCRYPTION_ALGORITHM is AES-256-GCM")

        assert config.ENCRYPTION_KDF == "PBKDF2-HMAC-SHA256"
        ok("ENCRYPTION_KDF is PBKDF2-HMAC-SHA256")

        assert config.ENCRYPTION_PBKDF2_ITERATIONS >= 100_000
        ok("PBKDF2 iterations are strong", str(config.ENCRYPTION_PBKDF2_ITERATIONS))

        assert config.ENCRYPTION_SALT_BYTES == 16
        assert config.ENCRYPTION_NONCE_BYTES == 12
        ok("salt=16 bytes, nonce=12 bytes")

        for d in (config.ENCRYPTED_DIR, config.DECRYPTED_DIR, config.DOWNLOADS_DIR):
            assert d.exists(), f"{d} should be auto-created"
        ok("encrypted/ decrypted/ downloads/ directories exist")
    except Exception as e:
        fail("config", str(e))


# ══════════════════════════════════════════════════════════════════
# 2. crypto_utils — salt / nonce / KDF
# ══════════════════════════════════════════════════════════════════

def test_crypto_primitives():
    section("crypto_utils.py — salt / nonce / KDF")
    try:
        from proof_client import crypto_utils as cu

        salt = cu.generate_salt()
        assert len(salt) == 16
        ok("generate_salt returns 16 bytes")

        nonce = cu.generate_nonce()
        assert len(nonce) == 12
        ok("generate_nonce returns 12 bytes")

        assert cu.generate_salt() != cu.generate_salt()
        ok("salts are random / unique")

        key1 = cu.derive_key_from_password("pw", salt, 1000)
        key2 = cu.derive_key_from_password("pw", salt, 1000)
        assert key1 == key2 and len(key1) == 32
        ok("PBKDF2 same password+salt → same 32-byte key")

        key3 = cu.derive_key_from_password("pw", cu.generate_salt(), 1000)
        assert key3 != key1
        ok("PBKDF2 different salt → different key")

        key4 = cu.derive_key_from_password("other", salt, 1000)
        assert key4 != key1
        ok("PBKDF2 different password → different key")

        try:
            cu.derive_key_from_password("", salt)
            fail("empty_password", "should have raised")
        except ValueError:
            ok("empty password rejected")
    except Exception as e:
        fail("crypto_primitives", str(e))


# ══════════════════════════════════════════════════════════════════
# 3. crypto_utils — encrypt / decrypt
# ══════════════════════════════════════════════════════════════════

def test_encrypt_decrypt():
    section("crypto_utils.py — encrypt / decrypt round-trip")
    try:
        from proof_client import crypto_utils as cu

        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src, enc, res = _encrypt_to(tmp)

            assert enc.exists()
            ok("encrypt_file writes ciphertext")

            assert enc.read_bytes() != src.read_bytes()
            ok("ciphertext differs from plaintext")

            assert res.original_sha256 == cu.sha256_of_bytes(src.read_bytes())
            ok("original_sha256 is correct")

            assert res.encrypted_sha256 == cu.sha256_of_bytes(enc.read_bytes())
            assert res.encrypted_sha256 != res.original_sha256
            ok("encrypted_sha256 is correct and distinct")

            assert len(bytes.fromhex(res.salt_hex)) == 16
            assert len(bytes.fromhex(res.nonce_hex)) == 12
            ok("result carries 16-byte salt + 12-byte nonce")

            # Correct password round-trips.
            out = tmp / "recovered.txt"
            cu.decrypt_file(enc, out, "correct horse", res.to_metadata())
            assert cu.sha256_of_bytes(out.read_bytes()) == res.original_sha256
            ok("correct password decrypts to original bytes")

            # Wrong password fails.
            try:
                cu.decrypt_file(enc, tmp / "x", "wrong", res.to_metadata())
                fail("wrong_password", "should have raised")
            except cu.DecryptionError:
                ok("wrong password raises DecryptionError")

            # Tampered ciphertext fails.
            blob = bytearray(enc.read_bytes())
            blob[0] ^= 0xFF
            (tmp / "tampered.enc").write_bytes(bytes(blob))
            try:
                cu.decrypt_file(tmp / "tampered.enc", tmp / "y", "correct horse", res.to_metadata())
                fail("tamper", "should have raised")
            except cu.DecryptionError:
                ok("tampered ciphertext raises DecryptionError")

            # Two encryptions of identical content differ (random salt/nonce).
            ct1 = enc.read_bytes()
            _, _, res2 = _encrypt_to(tmp)
            assert res2.salt_hex != res.salt_hex
            assert res2.encrypted_sha256 != res.encrypted_sha256
            assert enc.read_bytes() != ct1
            ok("re-encrypting same content yields different ciphertext")
    except Exception as e:
        fail("encrypt_decrypt", str(e))


# ══════════════════════════════════════════════════════════════════
# 4. crypto_utils — metadata carries no secrets
# ══════════════════════════════════════════════════════════════════

def test_metadata_no_secrets():
    section("crypto_utils.py — metadata excludes secrets")
    try:
        with tempfile.TemporaryDirectory() as t:
            _, _, res = _encrypt_to(Path(t))
            meta = res.to_metadata()
            blob = json.dumps(meta).lower()

            assert "password" not in meta and "key" not in meta
            ok("metadata dict has no 'password'/'key' keys")

            assert "correct horse" not in blob
            ok("metadata text does not contain the password")

            for required in ("salt_hex", "nonce_hex", "kdf_iterations", "algorithm"):
                assert required in meta
            ok("metadata carries public params (salt/nonce/kdf/algorithm)")

            d = res.to_dict()
            assert "password" not in d and "key" not in d
            ok("EncryptionResult.to_dict has no password/key")
    except Exception as e:
        fail("metadata_no_secrets", str(e))


# ══════════════════════════════════════════════════════════════════
# 5. encrypt_file / decrypt_file CLIs
# ══════════════════════════════════════════════════════════════════

def test_cli_encrypt_decrypt():
    section("encrypt_file.py / decrypt_file.py — CLI helpers")
    try:
        from proof_client import encrypt_file as ef
        from proof_client import decrypt_file as df

        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src = _make_plaintext(tmp, "paper.txt")
            enc_out = tmp / "paper.txt.enc"

            res = ef.run_encrypt(str(src), str(enc_out), "s3cret")
            assert enc_out.exists()
            ok("run_encrypt writes ciphertext")

            meta_path = ef.metadata_path_for(enc_out)
            assert meta_path.exists()
            ok("run_encrypt writes .metadata.json sidecar")

            meta = json.loads(meta_path.read_text())
            assert "password" not in json.dumps(meta).lower()
            ok("sidecar metadata contains no password")

            dec_out = tmp / "recovered.txt"
            df.run_decrypt(str(enc_out), str(meta_path), str(dec_out), "s3cret")
            assert dec_out.read_bytes() == src.read_bytes()
            ok("run_decrypt recovers the original bytes")

            # Default metadata/output path resolution.
            assert df._default_metadata(enc_out).name == "paper.txt.enc.metadata.json"
            assert df._default_output(enc_out).name == "paper.txt"
            ok("decrypt default metadata/output paths resolve correctly")

            # Password confirmation mismatch is caught.
            import builtins
            from unittest import mock
            with mock.patch("proof_client.encrypt_file.getpass", side_effect=["a", "b"]):
                try:
                    ef.prompt_new_password()
                    fail("confirm_mismatch", "should have raised")
                except ValueError:
                    ok("encrypt prompt rejects mismatched confirmation")
    except Exception as e:
        fail("cli_encrypt_decrypt", str(e))


# ══════════════════════════════════════════════════════════════════
# 6. EvidenceRecord — encryption fields + compatibility
# ══════════════════════════════════════════════════════════════════

def test_evidence_fields():
    section("evidence_schema.py — encryption fields")
    try:
        from proof_client.evidence_schema import EvidenceRecord

        plain = EvidenceRecord(file_name="a.txt", file_hash="0xabc", uri="u")
        assert plain.is_encrypted is False
        assert plain.encryption_algorithm == ""
        assert plain.encryption_kdf_iterations == 0
        assert plain.has_encrypted_ipfs is False
        ok("new encryption fields default correctly")

        # Backward compat: old JSON without the new keys still loads.
        old = {"file_name": "old.txt", "file_hash": "0xdead", "uri": "sepolia://old.txt"}
        rec = EvidenceRecord.from_dict(old)
        assert rec.is_encrypted is False and rec.encrypted_ipfs_cid == ""
        ok("pre-Stage-8 evidence JSON deserialises cleanly")

        # Round-trip via dict.
        with tempfile.TemporaryDirectory() as t:
            _, _, res = _encrypt_to(Path(t))
        enc_rec = _make_encrypted_record(res)
        again = EvidenceRecord.from_dict(enc_rec.to_dict())
        assert again.is_encrypted and again.encrypted_file_hash == res.encrypted_sha256
        ok("encrypted record survives to_dict/from_dict round-trip")

        assert enc_rec.has_encrypted_ipfs is True
        ok("has_encrypted_ipfs True for encrypted record")

        # file_hash stays the ORIGINAL hash, not the ciphertext hash.
        assert enc_rec.file_hash == res.original_sha256
        assert enc_rec.encrypted_file_hash != enc_rec.file_hash
        ok("file_hash == original; encrypted_file_hash is separate")
    except Exception as e:
        fail("evidence_fields", str(e))


# ══════════════════════════════════════════════════════════════════
# 7. SQLite migration + persistence
# ══════════════════════════════════════════════════════════════════

def test_sqlite_migration():
    section("evidence_repository.py — encryption column migration")
    try:
        from proof_client import evidence_repository as repo

        # ensure_column is idempotent.
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE evidence (id INTEGER PRIMARY KEY, file_name TEXT, "
            "file_hash TEXT, uri TEXT, created_at TEXT)"
        )
        repo.ensure_column(conn, "evidence", "is_encrypted", "INTEGER DEFAULT 0")
        repo.ensure_column(conn, "evidence", "is_encrypted", "INTEGER DEFAULT 0")
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(evidence)")}
        assert "is_encrypted" in cols
        ok("ensure_column adds a column and is idempotent")

        # _migrate adds all encryption columns to an old table.
        repo._migrate(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(evidence)")}
        for c in (
            "encryption_algorithm", "encryption_kdf", "encryption_kdf_iterations",
            "encryption_salt_hex", "encryption_nonce_hex", "encrypted_file_hash",
            "encrypted_file_name", "encrypted_ipfs_cid", "encrypted_ipfs_uri",
            "encrypted_ipfs_gateway_url", "encrypted_ipfs_provider",
            "encrypted_ipfs_uploaded_at",
        ):
            assert c in cols, f"missing column {c}"
        ok("_migrate adds every Stage 8 encryption column")
        conn.close()

        # Full insert + read round-trip on an isolated DB file.
        with tempfile.TemporaryDirectory() as t:
            with tempfile.TemporaryDirectory() as t2:
                _, _, res = _encrypt_to(Path(t2))
            enc_rec = _make_encrypted_record(res)

            original_db = repo.DB_PATH
            repo.DB_PATH = Path(t) / "evidence_test.db"
            try:
                repo.insert(enc_rec)
                fetched = repo.find_by_hash(res.original_sha256)
                assert fetched is not None
                assert fetched.is_encrypted
                assert fetched.encrypted_ipfs_cid == enc_rec.encrypted_ipfs_cid
                assert fetched.encrypted_file_hash == res.encrypted_sha256
                assert fetched.file_hash == res.original_sha256
                ok("repo.insert/find round-trips an encrypted record")
            finally:
                repo.DB_PATH = original_db
    except Exception as e:
        fail("sqlite_migration", str(e))


# ══════════════════════════════════════════════════════════════════
# 8. encrypted_ipfs — encrypt then upload
# ══════════════════════════════════════════════════════════════════

def test_encrypted_ipfs():
    section("encrypted_ipfs.py — encrypt then upload (mock)")
    try:
        from proof_client.encrypted_ipfs import encrypt_and_upload_to_ipfs
        from proof_client.ipfs_client import get_client
        from proof_client import crypto_utils as cu

        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src = _make_plaintext(tmp)
            info = encrypt_and_upload_to_ipfs(
                src, "pw", ipfs_provider="mock", output_dir=tmp
            )

            assert info["encrypted_ipfs_cid"].startswith("mock-")
            ok("encrypt_and_upload returns a mock CID")

            assert info["encrypted_ipfs_uri"] == f"ipfs://{info['encrypted_ipfs_cid']}"
            ok("encrypted_ipfs_uri is ipfs://<cid>")

            assert info["original_sha256"] != info["encrypted_sha256"]
            ok("returns distinct original + encrypted hashes")

            assert "password" not in json.dumps(info).lower()
            ok("upload info contains no password")

            # The CID stores the CIPHERTEXT — downloading it yields the
            # ciphertext hash, not the plaintext hash.
            out = tmp / "dl.enc"
            get_client("mock").download_file(info["encrypted_ipfs_cid"], out)
            assert cu.sha256_of_bytes(out.read_bytes()) == info["encrypted_sha256"]
            ok("IPFS-stored blob hashes to the ciphertext hash")
    except Exception as e:
        fail("encrypted_ipfs", str(e))


# ══════════════════════════════════════════════════════════════════
# 9. register_file — argument rules
# ══════════════════════════════════════════════════════════════════

def test_register_args():
    section("register_file.py — --encrypt-before-ipfs rules")
    try:
        from proof_client.register_file import _parse_args, register_file

        args = _parse_args(["works/x.txt", "--upload-ipfs", "--encrypt-before-ipfs"])
        assert args.encrypt_before_ipfs is True and args.upload_ipfs is True
        ok("--encrypt-before-ipfs parses with --upload-ipfs")

        args2 = _parse_args(["works/x.txt"])
        assert args2.encrypt_before_ipfs is False
        ok("--encrypt-before-ipfs defaults to False")

        # Using --encrypt-before-ipfs without --upload-ipfs is rejected.
        try:
            register_file("works/x.txt", encrypt_before_ipfs=True, upload_ipfs=False)
            fail("encrypt_without_upload", "should have raised")
        except ValueError as ve:
            assert "upload-ipfs" in str(ve)
            ok("encrypt_before_ipfs without upload_ipfs raises ValueError")
    except Exception as e:
        fail("register_args", str(e))


# ══════════════════════════════════════════════════════════════════
# 10. verify_encrypted_ipfs — success + failure
# ══════════════════════════════════════════════════════════════════

def test_verify_encrypted_ipfs():
    section("verify_encrypted_ipfs.py — verify loop")
    try:
        from proof_client.encrypted_ipfs import encrypt_and_upload_to_ipfs
        from proof_client.verify_encrypted_ipfs import verify_encrypted_ipfs
        from proof_client import crypto_utils as cu

        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src = _make_plaintext(tmp)
            info = encrypt_and_upload_to_ipfs(src, "pw", ipfs_provider="mock", output_dir=tmp)
            meta = {
                "salt_hex": info["salt_hex"],
                "nonce_hex": info["nonce_hex"],
                "kdf_iterations": info["kdf_iterations"],
            }

            res = verify_encrypted_ipfs(
                info["encrypted_ipfs_cid"], info["original_sha256"], meta, "pw",
                provider="mock", expected_encrypted_hash=info["encrypted_sha256"],
            )
            assert res["match"] is True
            ok("correct password → verification PASSED")

            assert res["ciphertext_hash_ok"] is True
            ok("downloaded ciphertext hash matches expected")

            assert res["decrypted_hash"] == info["original_sha256"]
            ok("decrypted hash equals the original file hash")

            # Wrong password raises (not a silent mismatch).
            try:
                verify_encrypted_ipfs(
                    info["encrypted_ipfs_cid"], info["original_sha256"], meta, "WRONG",
                    provider="mock",
                )
                fail("verify_wrong_pw", "should have raised")
            except cu.DecryptionError:
                ok("wrong password → DecryptionError")

            # Tampered-CID-content mismatch surfaces as match=False when the
            # expected encrypted hash differs.
            res_bad = verify_encrypted_ipfs(
                info["encrypted_ipfs_cid"], info["original_sha256"], meta, "pw",
                provider="mock", expected_encrypted_hash="0x" + "00" * 32,
            )
            assert res_bad["match"] is False and res_bad["ciphertext_hash_ok"] is False
            ok("ciphertext hash mismatch → match=False")
    except Exception as e:
        fail("verify_encrypted_ipfs", str(e))


# ══════════════════════════════════════════════════════════════════
# 11. Certificate (Markdown + PDF) encrypted section
# ══════════════════════════════════════════════════════════════════

def test_certificate():
    section("report_template.py / pdf_report.py — encrypted section")
    try:
        from proof_client.report_template import (
            build_certificate_data,
            build_markdown_certificate,
        )
        from proof_client.pdf_report import generate_pdf

        with tempfile.TemporaryDirectory() as t:
            _, _, res = _encrypt_to(Path(t))
        rec = _make_encrypted_record(res)

        d = build_certificate_data(rec)
        assert d["is_encrypted"] is True
        assert d["encryption_algorithm"] == "AES-256-GCM"
        assert d["encrypted_file_hash"] == res.encrypted_sha256
        ok("build_certificate_data includes encryption fields")

        md = build_markdown_certificate(rec)
        assert "Encrypted Off-Chain Storage" in md
        assert "AES-256-GCM" in md
        assert res.encrypted_sha256 in md
        ok("Markdown certificate has Encrypted Off-Chain Storage section")

        assert "password or encryption key is NOT stored" in md.replace("**", "")
        ok("certificate states the key/password is not stored")

        # All earlier sections (1..8) still present after renumber.
        for i in range(1, 9):
            assert f"{i}." in md, f"section {i} missing"
        ok("certificate retains sections 1-8")

        # Plain record shows 'No'.
        from proof_client.evidence_schema import EvidenceRecord
        plain = EvidenceRecord(file_name="p.txt", file_hash="0xabc", uri="u")
        md2 = build_markdown_certificate(plain)
        assert "Encrypted:** No" in md2 or "Encrypted: No" in md2.replace("**", "")
        ok("plain record certificate shows Encrypted: No")

        # PDF renders for an encrypted record.
        with tempfile.TemporaryDirectory() as t:
            from proof_client import config as cfg
            orig = cfg.REPORTS_DIR
            try:
                pdf = generate_pdf(rec)
                assert pdf.exists() and pdf.stat().st_size > 1000
                ok("PDF certificate generates for encrypted record")
            finally:
                pass
    except Exception as e:
        fail("certificate", str(e))


# ══════════════════════════════════════════════════════════════════
# 12. Verification guide — Step 5
# ══════════════════════════════════════════════════════════════════

def test_guide():
    section("verification_guide.py — Step 5 encrypted")
    try:
        from proof_client.verification_guide import (
            build_verification_guide,
            build_verification_commands,
        )
        from proof_client.evidence_schema import EvidenceRecord

        with tempfile.TemporaryDirectory() as t:
            _, _, res = _encrypt_to(Path(t))
        rec = _make_encrypted_record(res)

        guide = build_verification_guide(rec)
        assert "Step 5 — Verify Encrypted IPFS Content" in guide
        assert "verify_encrypted_ipfs --hash" in guide
        assert rec.encrypted_ipfs_cid in guide
        ok("guide has Step 5 with encrypted verification command")

        assert "password is never stored" in guide.lower()
        ok("guide states the password is never stored")

        cmds = build_verification_commands(rec)
        assert "verify_encrypted_ipfs" in cmds
        ok("commands file includes encrypted verification")

        # Plain record: Step 5 marked not applicable.
        plain = EvidenceRecord(file_name="p.txt", file_hash="0xabc", uri="u")
        guide2 = build_verification_guide(plain)
        assert "Step 5 — Verify Encrypted IPFS Content" in guide2
        assert "not stored as encrypted IPFS content" in guide2
        ok("plain record guide marks Step 5 not applicable")
    except Exception as e:
        fail("guide", str(e))


# ══════════════════════════════════════════════════════════════════
# 13. Evidence package — encrypted/ + original policy
# ══════════════════════════════════════════════════════════════════

def test_package():
    section("package_exporter.py — encrypted/ + original policy")
    try:
        from proof_client import config as cfg
        from proof_client.crypto_utils import encrypt_file
        from proof_client.package_exporter import (
            export_package,
            build_encryption_metadata,
        )
        from proof_client.manifest import verify_manifest

        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            # Put a plaintext in WORKS_DIR and a ciphertext in ENCRYPTED_DIR
            # so the packager can find both.
            src = cfg.WORKS_DIR / "pkg_demo_stage8.txt"
            src.write_bytes(b"package stage8 secret " * 40)
            enc_path = cfg.ENCRYPTED_DIR / "pkg_demo_stage8.txt.enc"
            res = encrypt_file(src, enc_path, "pw", iterations=_FAST_ITERS)

            rec = _make_encrypted_record(res)
            rec.file_name = "pkg_demo_stage8.txt"
            rec.encrypted_file_name = "pkg_demo_stage8.txt.enc"

            try:
                # Default: encrypted record EXCLUDES the plaintext original.
                pkg, zp = export_package(rec, tmp)
                files = {p.relative_to(pkg).as_posix() for p in pkg.rglob("*") if p.is_file()}

                assert "encrypted/encrypted_file.enc" in files
                ok("package contains encrypted/encrypted_file.enc")

                assert "encrypted/encryption_metadata.json" in files
                ok("package contains encrypted/encryption_metadata.json")

                meta = json.loads((pkg / "encrypted/encryption_metadata.json").read_text())
                assert "password" not in json.dumps(meta).lower() and "key" not in meta
                ok("package encryption metadata has no password/key")

                assert "original/README.md" in files
                assert "original/pkg_demo_stage8.txt" not in files
                ok("default encrypted package EXCLUDES the plaintext original")

                # manifest covers the encrypted file
                manifest = json.loads((pkg / "manifest.json").read_text())
                paths = [f["path"] for f in manifest["files"]]
                assert any("encrypted/encrypted_file.enc" in p for p in paths)
                ok("manifest covers the encrypted file")

                all_ok, errors = verify_manifest(pkg)
                assert all_ok, str(errors)
                ok("package manifest verifies clean")

                # --include-original bundles the plaintext.
                pkg2, _ = export_package(rec, tmp / "withorig", include_original=True)
                files2 = {p.relative_to(pkg2).as_posix() for p in pkg2.rglob("*") if p.is_file()}
                assert "original/pkg_demo_stage8.txt" in files2
                ok("--include-original bundles the plaintext original")

                # --exclude-original on a plain record drops the original.
                from proof_client.evidence_schema import EvidenceRecord
                plain = EvidenceRecord(
                    file_name="pkg_demo_stage8.txt", file_hash=res.original_sha256, uri="u"
                )
                pkg3, _ = export_package(plain, tmp / "plainexcl", include_original=False)
                files3 = {p.relative_to(pkg3).as_posix() for p in pkg3.rglob("*") if p.is_file()}
                assert "original/pkg_demo_stage8.txt" not in files3
                assert "original/README.md" in files3
                ok("--exclude-original drops the plaintext for a plain record")

                # build_encryption_metadata excludes secrets.
                emd = build_encryption_metadata(rec)
                assert "password" not in emd and "key" not in emd
                assert emd["original_sha256"] == res.original_sha256
                ok("build_encryption_metadata excludes secrets, keeps hashes")
            finally:
                src.unlink(missing_ok=True)
                enc_path.unlink(missing_ok=True)
                (cfg.ENCRYPTED_DIR / "pkg_demo_stage8.txt.enc.metadata.json").unlink(missing_ok=True)
    except Exception as e:
        fail("package", str(e))


# ══════════════════════════════════════════════════════════════════
# 14. Security invariant — no secrets anywhere
# ══════════════════════════════════════════════════════════════════

def test_security_invariants():
    section("security — passwords/keys never persisted")
    try:
        from proof_client import crypto_utils as cu
        from proof_client.encrypt_file import write_metadata

        password = "Sup3rSecretPassphrase!"
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src = _make_plaintext(tmp)
            enc = tmp / "s.enc"
            res = cu.encrypt_file(src, enc, password, iterations=_FAST_ITERS)

            # The ciphertext must not contain the password in plaintext.
            assert password.encode() not in enc.read_bytes()
            ok("ciphertext does not contain the password")

            # The sidecar metadata must not contain the password.
            meta_path = write_metadata(res, enc)
            assert password not in meta_path.read_text()
            ok("metadata sidecar does not contain the password")

            # The evidence record JSON must not contain the password.
            rec = _make_encrypted_record(res)
            assert password not in json.dumps(rec.to_dict())
            ok("evidence record JSON does not contain the password")

            # No 'key' field leaks the derived key.
            assert "derived_key" not in res.to_dict()
            ok("EncryptionResult never exposes the derived key")
    except Exception as e:
        fail("security_invariants", str(e))


# ══════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════

def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║          proof_client Stage 8 Test Suite                 ║")
    print("║  AES-256-GCM · PBKDF2 · Encrypted IPFS · Verify          ║")
    print("╚══════════════════════════════════════════════════════════╝")

    test_config()
    test_crypto_primitives()
    test_encrypt_decrypt()
    test_metadata_no_secrets()
    test_cli_encrypt_decrypt()
    test_evidence_fields()
    test_sqlite_migration()
    test_encrypted_ipfs()
    test_register_args()
    test_verify_encrypted_ipfs()
    test_certificate()
    test_guide()
    test_package()
    test_security_invariants()

    total = _passed + _failed
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print(f"║  📊 Results: {_passed}/{total} passed, {_failed} failed{' ' * (24 - len(str(_passed)) - len(str(total)) - len(str(_failed)))}║")
    print("╚══════════════════════════════════════════════════════════╝")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
