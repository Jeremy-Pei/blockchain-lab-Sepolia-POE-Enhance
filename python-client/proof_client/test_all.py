"""
test_all.py — Full module test suite

Test strategy:
  ┌─────────────────────────────────────────────────────────────────┐
  │ Layer 1: Pure local modules (no network / contract interaction) │
  │   config, hash_file, evidence_schema,                          │
  │   evidence_store, evidence_repository                          │
  │                                                                │
  │ Layer 2: Requires wallet but no on-chain interaction           │
  │   wallet (local key → address derivation only)                 │
  │                                                                │
  │ Layer 3: Requires on-chain interaction (RPC + contract calls)  │
  │   contract_client, register_file, verify_file, batch_register  │
  │                                                                │
  │ Layer 4: Depends on existing evidence data                     │
  │   generate_report, query_evidence                              │
  └─────────────────────────────────────────────────────────────────┘

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m proof_client.test_all          # local only
  PYTHONPATH=. .venv/bin/python -m proof_client.test_all --chain  # include on-chain
"""

import sys
import os
import tempfile
import json
from pathlib import Path

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
    print(f"  📦 {title}")
    print(f"{'━'*60}")


# ══════════════════════════════════════════════════════════════════
# Layer 1: Pure local modules
# ══════════════════════════════════════════════════════════════════

def test_config():
    """Test config.py — configuration loading and path constants."""
    section("config.py")
    try:
        from proof_client.config import (
            PROJECT_ROOT, ABI_DIR, WORKS_DIR, EVIDENCE_DIR,
            REPORTS_DIR, DB_PATH, RPC_URL, PRIVATE_KEY,
            CONTRACT_ADDRESS, CHAIN_ID, EXPLORER_TX_URL, load_abi,
        )

        # Path existence
        assert PROJECT_ROOT.exists(), "PROJECT_ROOT does not exist"
        ok("PROJECT_ROOT exists", str(PROJECT_ROOT))

        assert ABI_DIR.exists(), "ABI_DIR does not exist"
        ok("ABI_DIR exists")

        for name, d in [("WORKS_DIR", WORKS_DIR), ("EVIDENCE_DIR", EVIDENCE_DIR), ("REPORTS_DIR", REPORTS_DIR)]:
            assert d.exists(), f"{name} does not exist"
        ok("WORKS_DIR / EVIDENCE_DIR / REPORTS_DIR all exist")

        # Environment variables
        assert RPC_URL != "", "RPC_URL is empty"
        ok("RPC_URL loaded", RPC_URL[:40] + "...")

        assert PRIVATE_KEY != "", "PRIVATE_KEY is empty"
        ok("PRIVATE_KEY loaded", f"length={len(PRIVATE_KEY)}")

        assert CONTRACT_ADDRESS != "", "CONTRACT_ADDRESS is empty"
        ok("CONTRACT_ADDRESS loaded", CONTRACT_ADDRESS)

        assert CHAIN_ID == 11155111, f"CHAIN_ID should be 11155111, got {CHAIN_ID}"
        ok("CHAIN_ID correct", str(CHAIN_ID))

        assert "etherscan" in EXPLORER_TX_URL, "EXPLORER_TX_URL looks wrong"
        ok("EXPLORER_TX_URL correct", EXPLORER_TX_URL)

        # ABI loading
        abi = load_abi()
        assert isinstance(abi, list), "ABI should be a list"
        assert len(abi) == 3, f"ABI should have 3 items (register, verify, Registered), got {len(abi)}"
        func_names = {item.get("name") for item in abi}
        assert "register" in func_names, "ABI missing register"
        assert "verify" in func_names, "ABI missing verify"
        ok("load_abi()", f"{len(abi)} items: {func_names}")

    except Exception as e:
        fail("config", str(e))


def test_hash_file():
    """Test hash_file.py — SHA-256 hash computation."""
    section("hash_file.py")
    try:
        from proof_client.hash_file import sha256_hash

        # 1) Hash a known file
        works_file = Path("works/my_first_work.txt")
        if works_file.exists():
            h = sha256_hash(str(works_file))
            assert h.startswith("0x"), "Hash should start with 0x"
            assert len(h) == 66, f"Hash length should be 66 (0x + 64), got {len(h)}"
            ok("Known file hash", h[:20] + "...")
        else:
            fail("Known file", "works/my_first_work.txt not found")

        # 2) Hash a temp file twice → determinism check
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello blockchain")
            tmp_path = f.name

        h1 = sha256_hash(tmp_path)
        h2 = sha256_hash(tmp_path)
        assert h1 == h2, "Same file should produce the same hash twice"
        ok("Determinism check", "same file hashed twice → identical")
        os.unlink(tmp_path)

        # 3) Different content → different hash
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("content A")
            tmp_a = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("content B")
            tmp_b = f.name

        ha = sha256_hash(tmp_a)
        hb = sha256_hash(tmp_b)
        assert ha != hb, "Different content should produce different hashes"
        ok("Difference check", "different content → different hashes")
        os.unlink(tmp_a)
        os.unlink(tmp_b)

        # 4) Missing file → exception
        try:
            sha256_hash("/nonexistent/file.txt")
            fail("Exception handling", "Should have raised FileNotFoundError")
        except FileNotFoundError:
            ok("FileNotFoundError", "correctly raised for missing file")

    except Exception as e:
        fail("hash_file", str(e))


def test_evidence_schema():
    """Test evidence_schema.py — data structure and serialisation."""
    section("evidence_schema.py")
    try:
        from proof_client.evidence_schema import EvidenceRecord

        # 1) Create instance
        r = EvidenceRecord(
            file_name="test.txt",
            file_hash="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            uri="sepolia://test.txt",
            tx_hash="aabbccdd",
            block_number=12345,
            gas_used=50000,
            owner="0x1234567890abcdef1234567890abcdef12345678",
            timestamp=1718000000,
            status="success",
            contract_address="0xContractAddress",
            explorer_tx_url="https://sepolia.etherscan.io/tx/",
        )
        ok("Create instance", f"file_name={r.file_name}")

        # 2) to_dict
        d = r.to_dict()
        assert isinstance(d, dict), "to_dict should return a dict"
        assert d["file_name"] == "test.txt"
        assert d["block_number"] == 12345
        ok("to_dict", f"{len(d)} fields")

        # 3) from_dict (normal)
        r2 = EvidenceRecord.from_dict(d)
        assert r2.file_name == r.file_name
        assert r2.block_number == r.block_number
        ok("from_dict (normal)", f"file={r2.file_name}, block={r2.block_number}")

        # 4) from_dict (extra fields → should be ignored)
        d_extra = {**d, "unknown_field": "should_be_ignored", "id": 999}
        r3 = EvidenceRecord.from_dict(d_extra)
        assert r3.file_name == "test.txt"
        ok("from_dict filters unknown keys", "extra fields safely ignored")

        # 5) timestamp_utc property
        assert r.timestamp_utc != "N/A", "Should not be N/A when timestamp is set"
        assert "UTC" in r.timestamp_utc
        ok("timestamp_utc", r.timestamp_utc)

        # 6) timestamp_utc when timestamp is 0
        r_zero = EvidenceRecord(file_name="x", file_hash="0x00", uri="x", timestamp=0)
        assert r_zero.timestamp_utc == "N/A"
        ok("timestamp_utc (zero)", "returns N/A")

        # 7) explorer_link property
        assert r.explorer_link.startswith("https://")
        assert "aabbccdd" in r.explorer_link
        ok("explorer_link", r.explorer_link)

        # 8) explorer_link when empty
        r_empty = EvidenceRecord(file_name="x", file_hash="0x00", uri="x")
        assert r_empty.explorer_link == ""
        ok("explorer_link (empty)", "returns empty string")

    except Exception as e:
        fail("evidence_schema", str(e))


def test_evidence_store():
    """Test evidence_store.py — JSON file persistence."""
    section("evidence_store.py")
    try:
        from proof_client.evidence_schema import EvidenceRecord
        from proof_client.evidence_store import save_evidence, load_evidence, list_all_evidence
        from proof_client.config import EVIDENCE_DIR

        test_hash = "0x_test_store_1234567890abcdef1234567890abcdef1234567890abcdef12345678"

        r = EvidenceRecord(
            file_name="store_test.txt",
            file_hash=test_hash,
            uri="sepolia://store_test.txt",
            status="success",
        )

        # 1) Save
        path = save_evidence(r)
        assert path.exists(), "File should exist after saving"
        ok("save_evidence", str(path.name))

        # 2) Load
        loaded = load_evidence(test_hash)
        assert loaded is not None, "Should be able to load the saved evidence"
        assert loaded.file_name == "store_test.txt"
        assert loaded.file_hash == test_hash
        ok("load_evidence", f"file={loaded.file_name}")

        # 3) Load non-existent hash
        missing = load_evidence("0xnon_existent_hash_0000000000000000000000000000000000000000")
        assert missing is None, "Non-existent hash should return None"
        ok("load_evidence (missing)", "returns None")

        # 4) list_all_evidence
        all_records = list_all_evidence()
        assert any(r.file_hash == test_hash for r in all_records)
        ok("list_all_evidence", f"{len(all_records)} record(s)")

        # 5) JSON content validation
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["file_name"] == "store_test.txt"
        assert data["status"] == "success"
        ok("JSON content correct", "field values match")

        # Cleanup
        path.unlink()
        ok("Cleanup test file")

    except Exception as e:
        fail("evidence_store", str(e))


def test_evidence_repository():
    """Test evidence_repository.py — SQLite persistence."""
    section("evidence_repository.py")
    try:
        from proof_client.evidence_schema import EvidenceRecord
        from proof_client import evidence_repository as repo
        from proof_client.config import DB_PATH

        test_hash = "0x_test_repo_unique_hash_" + "a" * 40

        r = EvidenceRecord(
            file_name="repo_test.txt",
            file_hash=test_hash,
            uri="sepolia://repo_test.txt",
            owner="0xTestOwnerAddress",
            status="success",
        )

        # 1) count (initial)
        count_before = repo.count()
        ok("count()", f"current count={count_before}")

        # 2) insert
        rowid = repo.insert(r)
        assert rowid > 0, "insert should return a positive rowid"
        ok("insert", f"rowid={rowid}")

        # 3) count (after insert)
        count_after = repo.count()
        assert count_after == count_before + 1
        ok("count() incremented", f"{count_before} → {count_after}")

        # 4) find_by_hash
        found = repo.find_by_hash(test_hash)
        assert found is not None
        assert found.file_name == "repo_test.txt"
        ok("find_by_hash", f"file={found.file_name}")

        # 5) find_by_hash (missing)
        not_found = repo.find_by_hash("0xnon_existent_" + "b" * 50)
        assert not_found is None
        ok("find_by_hash (missing)", "returns None")

        # 6) find_by_owner
        by_owner = repo.find_by_owner("0xTestOwnerAddress")
        assert len(by_owner) >= 1
        assert any(r.file_hash == test_hash for r in by_owner)
        ok("find_by_owner", f"found {len(by_owner)} record(s)")

        # 7) find_all
        all_records = repo.find_all()
        assert len(all_records) >= 1
        ok("find_all", f"{len(all_records)} total record(s)")

        # 8) Duplicate insert → should fail (UNIQUE constraint)
        try:
            repo.insert(r)
            fail("UNIQUE constraint", "Duplicate insert should raise an error")
        except Exception:
            ok("UNIQUE constraint", "duplicate hash correctly rejected")

        # Cleanup: remove test database
        if DB_PATH.exists():
            DB_PATH.unlink()
            ok("Cleanup test database")

    except Exception as e:
        fail("evidence_repository", str(e))


# ══════════════════════════════════════════════════════════════════
# Layer 2: Wallet (local key derivation, no network needed)
# ══════════════════════════════════════════════════════════════════

def test_wallet():
    """Test wallet.py — local key derivation."""
    section("wallet.py")
    try:
        from proof_client.wallet import get_account, get_address, get_chain_id

        # 1) get_account
        account = get_account()
        assert account is not None
        assert hasattr(account, "address")
        ok("get_account", f"type={type(account).__name__}")

        # 2) get_address
        addr = get_address()
        assert addr.startswith("0x"), "Address should start with 0x"
        assert len(addr) == 42, f"Address length should be 42, got {len(addr)}"
        ok("get_address", addr)

        # 3) get_chain_id
        chain_id = get_chain_id()
        assert chain_id == 11155111
        ok("get_chain_id", str(chain_id))

        # 4) Address consistency
        assert account.address == addr
        ok("Address consistency", "account.address == get_address()")

    except Exception as e:
        fail("wallet", str(e))


# ══════════════════════════════════════════════════════════════════
# Layer 3: On-chain interaction (requires --chain flag)
# ══════════════════════════════════════════════════════════════════

def test_contract_client():
    """Test contract_client.py — contract connection and verify."""
    section("contract_client.py (on-chain)")
    try:
        from proof_client.contract_client import verify_hash

        # verify a non-existent hash → should return timestamp=0
        fake_hash = "0x0000000000000000000000000000000000000000000000000000000000000001"
        result = verify_hash(fake_hash)
        assert "registered" in result
        assert "owner" in result
        assert "timestamp" in result
        ok("verify_hash (unregistered)", f"registered={result['registered']}")

    except ConnectionError as e:
        fail("contract_client", f"Cannot connect to RPC: {e}")
    except Exception as e:
        fail("contract_client", str(e))


def test_register_and_verify():
    """Test register_file + verify_file end-to-end flow."""
    section("register_file + verify_file (on-chain end-to-end)")
    try:
        import tempfile
        from proof_client.register_file import register_file
        from proof_client.verify_file import verify_file
        from proof_client.config import EVIDENCE_DIR, DB_PATH

        # Create a temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False,
            dir=str(Path("works")),
            prefix="chain_test_",
        ) as f:
            f.write(f"chain test file - unique content {os.urandom(8).hex()}")
            tmp_path = f.name

        # 1) Register
        record = register_file(tmp_path)
        assert record.status == "success"
        assert record.tx_hash != ""
        assert record.block_number > 0
        ok("register_file", f"tx=0x{record.tx_hash[:16]}..., block={record.block_number}")

        # 2) Verify
        result = verify_file(tmp_path)
        assert result["registered"] is True
        assert result["chain_data"]["owner"] != "0x" + "0" * 40
        ok("verify_file", f"owner={result['chain_data']['owner'][:16]}...")

        # 3) Local evidence exists
        assert result["local_evidence"] is not None
        ok("Local evidence saved", f"file={result['local_evidence'].file_name}")

        # Cleanup
        os.unlink(tmp_path)
        evidence_file = EVIDENCE_DIR / f"evidence_{record.file_hash.replace('0x','')[:8]}.json"
        if evidence_file.exists():
            evidence_file.unlink()
        if DB_PATH.exists():
            DB_PATH.unlink()
        ok("Cleanup test data")

    except ConnectionError as e:
        fail("register+verify", f"Cannot connect to RPC: {e}")
    except Exception as e:
        fail("register+verify", str(e))


# ══════════════════════════════════════════════════════════════════
# Layer 4: Reports and queries (depend on existing data)
# ══════════════════════════════════════════════════════════════════

def test_generate_report():
    """Test generate_report.py — report generation."""
    section("generate_report.py")
    try:
        from proof_client.evidence_schema import EvidenceRecord
        from proof_client.evidence_store import save_evidence
        from proof_client.generate_report import generate_report
        from proof_client.config import EVIDENCE_DIR, REPORTS_DIR

        test_hash = "0x_test_report_hash_" + "c" * 44

        # Save a test evidence record first
        r = EvidenceRecord(
            file_name="report_test.txt",
            file_hash=test_hash,
            uri="sepolia://report_test.txt",
            tx_hash="deadbeef" * 8,
            block_number=99999,
            gas_used=21000,
            owner="0xReportTestOwner",
            timestamp=1718000000,
            status="success",
            contract_address="0xContractAddr",
            explorer_tx_url="https://sepolia.etherscan.io/tx/",
        )
        evidence_path = save_evidence(r)

        # 1) Generate report
        report_path = generate_report(test_hash)
        assert report_path is not None, "generate_report should return a path"
        assert report_path.exists(), "Report file should exist"
        ok("generate_report", str(report_path.name))

        # 2) Content check
        content = report_path.read_text(encoding="utf-8")
        assert "report_test.txt" in content
        assert "Proof of Existence" in content
        assert "How to Verify" in content
        ok("Report content correct", f"length={len(content)} chars")

        # 3) Non-existent hash
        result = generate_report("0xnon_existent_" + "d" * 50)
        assert result is None
        ok("generate_report (missing)", "returns None")

        # Cleanup
        evidence_path.unlink()
        report_path.unlink()
        ok("Cleanup test files")

    except Exception as e:
        fail("generate_report", str(e))


def test_query_evidence():
    """Test query_evidence.py — query functionality."""
    section("query_evidence.py")
    try:
        from proof_client.evidence_schema import EvidenceRecord
        from proof_client import evidence_repository as repo
        from proof_client.query_evidence import query_all, query_by_hash, query_by_owner, query_stats
        from proof_client.config import DB_PATH

        test_hash = "0x_test_query_hash_" + "e" * 44

        # Insert test data
        r = EvidenceRecord(
            file_name="query_test.txt",
            file_hash=test_hash,
            uri="sepolia://query_test.txt",
            owner="0xQueryTestOwner",
            status="success",
        )
        repo.insert(r)

        # 1) query_all (no exception expected)
        query_all()
        ok("query_all", "no exception")

        # 2) query_by_hash
        query_by_hash(test_hash)
        ok("query_by_hash", "no exception")

        # 3) query_by_owner
        query_by_owner("0xQueryTestOwner")
        ok("query_by_owner", "no exception")

        # 4) query_stats
        query_stats()
        ok("query_stats", "no exception")

        # Cleanup
        if DB_PATH.exists():
            DB_PATH.unlink()
        ok("Cleanup test database")

    except Exception as e:
        fail("query_evidence", str(e))


# ══════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════

def main():
    run_chain = "--chain" in sys.argv

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║            proof_client Full Test Suite                  ║")
    print(f"║  Mode: {'local + on-chain' if run_chain else 'local only (use --chain to include on-chain)'}{'   ' if run_chain else ''}  ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # Layer 1: Pure local
    test_config()
    test_hash_file()
    test_evidence_schema()
    test_evidence_store()
    test_evidence_repository()

    # Layer 2: Wallet
    test_wallet()

    # Layer 3: On-chain interaction
    if run_chain:
        test_contract_client()
        test_register_and_verify()
    else:
        section("Skipping on-chain tests (pass --chain to enable)")

    # Layer 4: Reports and queries
    test_generate_report()
    test_query_evidence()

    # Summary
    total = _passed + _failed
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print(f"║  📊 Results: {_passed}/{total} passed, {_failed} failed                          ║")
    print("╚══════════════════════════════════════════════════════════╝")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
