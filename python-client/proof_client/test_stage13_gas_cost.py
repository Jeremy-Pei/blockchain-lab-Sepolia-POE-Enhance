"""
test_stage13_gas_cost.py — Stage 13 test suite (gas cost model)

Tests:
  1. GasCost calculation
  2. Merkle savings percentage
  3. EvidenceRecord gas fields
  4. BatchEvidence gas fields
  5. SQLite gas column migrations
  6. register_hash returns effective gas price
  7. register_file stores gas cost fields

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m proof_client.test_stage13_gas_cost
"""

import sqlite3
import sys
import tempfile
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


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        ok(name, detail)
    else:
        fail(name, detail or "assertion failed")


def section(title: str):
    print(f"\n{'━'*60}")
    print(f"  ⛽ {title}")
    print(f"{'━'*60}")


# ══════════════════════════════════════════════════════════════════
# 1. GasCost calculation
# ══════════════════════════════════════════════════════════════════


def test_gas_cost_calculation():
    section("GasCost Calculation")
    from proof_client.gas_cost import calculate_gas_cost

    c = calculate_gas_cost(50_000, 2_000_000_000)
    check("T01 total fee = gas × price",
          c.total_fee_wei == 100_000_000_000_000)
    check("T02 total fee in ETH", c.total_fee_eth == "0.0001")
    check("T03 default file_count is 1", c.file_count == 1)
    check("T04 cost per file equals total for 1 file",
          c.cost_per_file_wei == c.total_fee_wei)
    check("T05 default symbol ETH", c.native_token_symbol == "ETH")

    c5 = calculate_gas_cost(50_000, 2_000_000_000, file_count=5)
    check("T06 per-file cost divides by file_count",
          c5.cost_per_file_wei == 20_000_000_000_000)
    check("T07 per-file cost in ETH", c5.cost_per_file_eth == "0.00002")
    check("T08 file_count stored", c5.file_count == 5)

    c0 = calculate_gas_cost(50_000, 2_000_000_000, file_count=0)
    check("T09 file_count 0 does not divide by zero",
          c0.cost_per_file_wei == c0.total_fee_wei)

    cz = calculate_gas_cost(0, 0)
    check("T10 zero gas → zero fee", cz.total_fee_wei == 0)
    check("T11 zero fee in ETH", cz.total_fee_eth == "0")

    cs = calculate_gas_cost(21_000, 1_000_000_000, native_token_symbol="MATIC")
    check("T12 custom token symbol", cs.native_token_symbol == "MATIC")

    d = c5.to_dict()
    check("T13 to_dict has all cost keys",
          all(k in d for k in ("gas_used", "effective_gas_price_wei",
                               "total_fee_wei", "total_fee_eth",
                               "cost_per_file_wei", "cost_per_file_eth",
                               "native_token_symbol", "file_count")))


# ══════════════════════════════════════════════════════════════════
# 2. Merkle savings
# ══════════════════════════════════════════════════════════════════


def test_merkle_savings():
    section("Merkle Savings Percentage")
    from proof_client.gas_cost import merkle_savings_percentage

    check("T14 90% saving", merkle_savings_percentage(100, 10) == 90.0)
    check("T15 no saving when equal", merkle_savings_percentage(100, 100) == 0.0)
    check("T16 full saving when merkle free",
          merkle_savings_percentage(100, 0) == 100.0)
    check("T17 zero single cost → 0.0",
          merkle_savings_percentage(0, 10) == 0.0)
    check("T18 negative saving when merkle costs more",
          merkle_savings_percentage(100, 150) == -50.0)
    check("T19 fractional saving",
          abs(merkle_savings_percentage(3, 1) - 66.6667) < 0.01)


# ══════════════════════════════════════════════════════════════════
# 3. EvidenceRecord gas fields
# ══════════════════════════════════════════════════════════════════


def test_evidence_record_gas_fields():
    section("EvidenceRecord Gas Fields")
    from proof_client.evidence_schema import EvidenceRecord

    r = EvidenceRecord(file_name="a.txt", file_hash="0xaa", uri="x")
    for i, f in enumerate(("effective_gas_price_wei", "total_fee_wei",
                           "total_fee_eth", "native_token_symbol"), start=20):
        check(f"T{i} has {f} field", hasattr(r, f))
    check("T24 gas fields default to zero/empty",
          r.effective_gas_price_wei == 0 and r.total_fee_wei == 0
          and r.total_fee_eth == "" and r.native_token_symbol == "")

    r2 = EvidenceRecord(
        file_name="b.txt", file_hash="0xbb", uri="y",
        gas_used=48_000, effective_gas_price_wei=1_500_000_000,
        total_fee_wei=72_000_000_000_000, total_fee_eth="0.000072",
        native_token_symbol="ETH",
    )
    check("T25 gas fields stored", r2.total_fee_eth == "0.000072")

    d = r2.to_dict()
    check("T26 gas fields serialise",
          d["effective_gas_price_wei"] == 1_500_000_000
          and d["total_fee_wei"] == 72_000_000_000_000)

    old = {"file_name": "c.txt", "file_hash": "0xcc", "uri": "z"}
    r3 = EvidenceRecord.from_dict(old)
    check("T27 pre-Stage-13 record deserialises",
          r3.total_fee_wei == 0 and r3.total_fee_eth == "")


# ══════════════════════════════════════════════════════════════════
# 4. BatchEvidence gas fields
# ══════════════════════════════════════════════════════════════════


def test_batch_evidence_gas_fields():
    section("BatchEvidence Gas Fields")
    from proof_client.merkle_evidence import BatchEvidence

    be = BatchEvidence()
    for i, f in enumerate(("gas_used", "effective_gas_price_wei",
                           "total_fee_wei", "total_fee_eth",
                           "cost_per_file_wei", "cost_per_file_eth",
                           "native_token_symbol"), start=28):
        check(f"T{i} has {f} field", hasattr(be, f))

    be2 = BatchEvidence(
        batch_id="b1", merkle_root="0xroot", file_count=10,
        gas_used=60_000, effective_gas_price_wei=2_000_000_000,
        total_fee_wei=120_000_000_000_000, total_fee_eth="0.00012",
        cost_per_file_wei=12_000_000_000_000, cost_per_file_eth="0.000012",
        native_token_symbol="ETH",
    )
    check("T35 batch gas fields stored",
          be2.cost_per_file_wei == 12_000_000_000_000)

    d = be2.to_dict()
    check("T36 batch gas fields serialise",
          d["total_fee_eth"] == "0.00012" and d["cost_per_file_eth"] == "0.000012")


# ══════════════════════════════════════════════════════════════════
# 5. SQLite migrations
# ══════════════════════════════════════════════════════════════════


def test_sqlite_gas_migration():
    section("SQLite Gas Column Migration")
    import proof_client.evidence_repository as repo_mod

    tmp = Path(tempfile.mkdtemp(prefix="stage13_gas_db_"))
    db_path = tmp / "old.db"

    # Old-style DB without Stage 13 columns
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL, file_hash TEXT NOT NULL UNIQUE,
            uri TEXT NOT NULL, created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE batch_evidence_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL UNIQUE,
            merkle_root TEXT NOT NULL UNIQUE,
            created_at_utc TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO evidence (file_name, file_hash, uri, created_at) "
        "VALUES ('old.txt', '0xold', 'x', '2024-01-01')"
    )
    conn.commit()
    conn.close()

    conn2 = repo_mod._get_conn(db_path)
    cols = {r["name"] for r in conn2.execute("PRAGMA table_info(evidence)")}
    for i, col in enumerate(("effective_gas_price_wei", "total_fee_wei",
                             "total_fee_eth", "native_token_symbol"), start=37):
        check(f"T{i} evidence.{col} migrated", col in cols)
    row = conn2.execute("SELECT * FROM evidence WHERE file_hash='0xold'").fetchone()
    check("T41 old evidence row still readable", row is not None)
    check("T42 migrated gas column defaults to 0",
          row["total_fee_wei"] == 0)
    conn2.close()

    conn3 = repo_mod._get_batch_conn(db_path)
    bcols = {r["name"] for r in conn3.execute(
        "PRAGMA table_info(batch_evidence_records)")}
    for i, col in enumerate(("gas_used", "effective_gas_price_wei",
                             "total_fee_wei", "total_fee_eth",
                             "cost_per_file_wei", "cost_per_file_eth",
                             "native_token_symbol"), start=43):
        check(f"T{i} batch.{col} migrated", col in bcols)
    conn3.close()

    # Batch insert stores the gas fields (fresh DB with the full schema)
    from proof_client.evidence_repository import (
        find_batch_by_id,
        insert_batch_evidence,
    )
    db_path = tmp / "fresh.db"
    insert_batch_evidence({
        "batch_id": "gas-batch", "merkle_root": "0xgasroot",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "network_key": "anvil", "gas_used": 60_000,
        "effective_gas_price_wei": 2_000_000_000,
        "total_fee_wei": 120_000_000_000_000, "total_fee_eth": "0.00012",
        "cost_per_file_wei": 12_000_000_000_000,
        "cost_per_file_eth": "0.000012", "native_token_symbol": "ETH",
    }, db_path=db_path)
    saved = find_batch_by_id("gas-batch", db_path=db_path)
    check("T50 batch insert stores gas_used", saved["gas_used"] == 60_000)
    check("T51 batch insert stores total_fee_eth",
          saved["total_fee_eth"] == "0.00012")
    check("T52 batch insert stores cost_per_file_eth",
          saved["cost_per_file_eth"] == "0.000012")
    check("T53 batch insert stores network_key",
          saved["network_key"] == "anvil")


# ══════════════════════════════════════════════════════════════════
# 6. register_file gas integration
# ══════════════════════════════════════════════════════════════════


def test_register_file_gas_integration():
    section("register_file Gas Integration")
    import proof_client.evidence_repository as repo_mod
    import proof_client.evidence_store as store_mod
    import proof_client.register_file as reg_mod

    tmp = Path(tempfile.mkdtemp(prefix="stage13_reg_gas_"))
    repo_mod.DB_PATH = tmp / "t.db"
    store_mod.EVIDENCE_DIR = tmp / "evidence"
    store_mod.EVIDENCE_DIR.mkdir()

    test_file = tmp / "gas.txt"
    test_file.write_bytes(b"stage 13 gas content")

    _MOCK_TX = {
        "tx_hash": "aa" * 32,
        "block_number": 7,
        "gas_used": 48_000,
        "effective_gas_price_wei": 1_500_000_000,
        "status": "success",
        "contract_address": "0xC",
        "network_key": "sepolia",
    }

    original_rh = reg_mod.register_hash
    original_ga = reg_mod.get_address
    try:
        reg_mod.register_hash = lambda fh, uri, network_key=None: dict(_MOCK_TX)
        reg_mod.get_address = lambda: "0xDEAD"

        record = reg_mod.register_file(str(test_file), network_key="sepolia")
        check("T54 gas_used stored", record.gas_used == 48_000)
        check("T55 effective_gas_price stored",
              record.effective_gas_price_wei == 1_500_000_000)
        check("T56 total_fee = gas × price",
              record.total_fee_wei == 48_000 * 1_500_000_000)
        check("T57 total_fee_eth computed",
              record.total_fee_eth == "0.000072")
        check("T58 native token symbol from network config",
              record.native_token_symbol == "ETH")

        # Legacy tx result without effective_gas_price_wei still works
        legacy_tx = {k: v for k, v in _MOCK_TX.items()
                     if k != "effective_gas_price_wei"}
        reg_mod.register_hash = lambda fh, uri, network_key=None: dict(legacy_tx)
        test_file2 = tmp / "gas2.txt"
        test_file2.write_bytes(b"stage 13 legacy tx result")
        record2 = reg_mod.register_file(str(test_file2), network_key="sepolia")
        check("T59 legacy tx result → zero fee, no crash",
              record2.total_fee_wei == 0)
    finally:
        reg_mod.register_hash = original_rh
        reg_mod.get_address = original_ga


# ══════════════════════════════════════════════════════════════════
# 7. Batch registration gas integration
# ══════════════════════════════════════════════════════════════════


def test_batch_register_gas_integration():
    section("Batch Registration Gas Integration")
    from proof_client.gas_cost import calculate_gas_cost

    # The batch flow amortises one tx over N leaves; verify the maths the
    # flow relies on for a realistic batch.
    cost = calculate_gas_cost(
        gas_used=60_000, effective_gas_price_wei=2_000_000_000,
        file_count=10, native_token_symbol="ETH",
    )
    check("T60 batch total fee", cost.total_fee_wei == 120_000_000_000_000)
    check("T61 batch cost per file",
          cost.cost_per_file_wei == 12_000_000_000_000)
    check("T62 batch cost per file eth", cost.cost_per_file_eth == "0.000012")

    # Dry-run batch evidence carries zeroed gas fields
    import proof_client.batch_merkle_register as batch_mod
    import proof_client.evidence_repository as repo_mod
    import proof_client.merkle_evidence as me_mod

    tmp = Path(tempfile.mkdtemp(prefix="stage13_batch_gas_"))
    repo_mod.DB_PATH = tmp / "b.db"
    # Redirect all batch output directories into the temp dir.
    batch_mod.BATCH_EVIDENCE_DIR = tmp / "evidence"
    batch_mod.BATCH_PACKAGES_DIR = tmp / "packages"
    batch_mod.BATCH_REPORTS_DIR = tmp / "reports"
    me_mod.BATCH_EVIDENCE_DIR = tmp / "evidence"
    for d in (batch_mod.BATCH_EVIDENCE_DIR, batch_mod.BATCH_PACKAGES_DIR,
              batch_mod.BATCH_REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    src = tmp / "src"
    src.mkdir()
    (src / "a.txt").write_text("file a")
    (src / "b.txt").write_text("file b")

    result = batch_mod.run_batch_registration(src, dry_run=True,
                                              network_key="sepolia")
    check("T63 dry-run batch completes", result["file_count"] == 2)

    from proof_client.evidence_repository import find_batch_by_id
    saved = find_batch_by_id(result["batch_id"], db_path=repo_mod.DB_PATH)
    check("T64 dry-run batch stored with zero gas",
          saved is not None and saved["gas_used"] == 0)
    check("T65 dry-run batch keeps native symbol",
          saved["native_token_symbol"] == "ETH")


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print("  Stage 13 Test Suite — Gas Cost Model")
    print("=" * 60)

    test_gas_cost_calculation()
    test_merkle_savings()
    test_evidence_record_gas_fields()
    test_batch_evidence_gas_fields()
    test_sqlite_gas_migration()
    test_register_file_gas_integration()
    test_batch_register_gas_integration()

    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  Stage 13 Gas Cost Results: {_passed}/{total} passed, {_failed} failed")
    print(f"{'=' * 60}\n")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
