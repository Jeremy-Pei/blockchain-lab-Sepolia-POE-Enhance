"""
test_stage13_gas_study.py — Stage 13 test suite (gas study + reports)

Tests:
  1. Deterministic sample generation
  2. GasStudyRecord schema
  3. Study record building
  4. Full mocked gas study run (outputs, CSV, README)
  5. Workflow selection flags
  6. Dry-run behaviour
  7. Report aggregation (summaries, Merkle savings)
  8. Markdown / PDF report generation
  9. CLI argument parsing + confirm gate

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m proof_client.test_stage13_gas_study
"""

import csv
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

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
    print(f"  📊 {title}")
    print(f"{'━'*60}")


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="stage13_study_"))


def _fake_register_factory(calls: list, gas_used: int = 48_000,
                           gas_price: int = 1_500_000_000):
    def fake_register(fh, uri, network_key=None):
        calls.append({"file_hash": fh, "uri": uri, "network_key": network_key})
        return {
            "tx_hash": f"{len(calls):02d}" * 32,
            "block_number": len(calls),
            "gas_used": gas_used,
            "effective_gas_price_wei": gas_price,
            "status": "success",
            "contract_address": "0xSTUDYCONTRACT",
            "network_key": network_key,
        }
    return fake_register


# ══════════════════════════════════════════════════════════════════
# 1. Sample generation
# ══════════════════════════════════════════════════════════════════


def test_sample_generation():
    section("Deterministic Sample Generation")
    from proof_client.generate_gas_samples import generate_gas_samples, sample_content

    tmp = _tmp()

    paths = generate_gas_samples(tmp / "s", count=5, salt="abc")
    check("T01 generates requested count", len(paths) == 5)
    check("T02 files named file_NNN.txt", paths[0].name == "file_001.txt")
    check("T03 all files exist", all(p.exists() for p in paths))

    again = generate_gas_samples(tmp / "s2", count=5, salt="abc")
    check("T04 same salt → identical bytes",
          [p.read_bytes() for p in paths] == [p.read_bytes() for p in again])

    other = generate_gas_samples(tmp / "s3", count=5, salt="xyz")
    check("T05 different salt → different bytes",
          paths[0].read_bytes() != other[0].read_bytes())

    check("T06 different index → different content",
          sample_content(1, "a") != sample_content(2, "a"))
    check("T07 no-salt content is deterministic",
          sample_content(3) == sample_content(3))
    check("T08 salt appears in content", "abc" in sample_content(1, "abc"))

    try:
        generate_gas_samples(tmp / "bad", count=0)
        fail("T09 count 0 raises ValueError", "did not raise")
    except ValueError:
        ok("T09 count 0 raises ValueError")


# ══════════════════════════════════════════════════════════════════
# 2. GasStudyRecord schema
# ══════════════════════════════════════════════════════════════════


def test_gas_study_record():
    section("GasStudyRecord Schema")
    from proof_client.gas_study import GasStudyRecord, make_study_id

    sid = make_study_id()
    check("T10 study id prefixed", sid.startswith("gas_study_"))
    check("T11 study id timestamped", len(sid) == len("gas_study_20260702_120000"))

    r = GasStudyRecord(
        study_id=sid, workflow="single_file", network_key="anvil",
        network_display_name="Anvil Local", chain_id=31337,
        contract_address="0xC", transaction_hash="0x" + "aa" * 32,
        block_number=1, gas_used=48_000,
        effective_gas_price_wei=1_500_000_000,
        total_fee_wei=72_000_000_000_000, total_fee_eth="0.000072",
        native_token_symbol="ETH", file_count=1,
        cost_per_file_wei=72_000_000_000_000, cost_per_file_eth="0.000072",
    )
    check("T12 created_at auto-filled", bool(r.created_at_utc))
    check("T13 merkle_root defaults empty", r.merkle_root == "")

    d = r.to_dict()
    check("T14 to_dict round-trips",
          GasStudyRecord.from_dict(d).to_dict() == d)
    check("T15 from_dict filters unknown keys",
          GasStudyRecord.from_dict({**d, "bogus": 1}).workflow == "single_file")


# ══════════════════════════════════════════════════════════════════
# 3. Study record building
# ══════════════════════════════════════════════════════════════════


def test_build_study_record():
    section("Study Record Building")
    from proof_client.gas_study import build_study_record
    from proof_client.network_config import load_network_config

    cfg = load_network_config("sepolia")
    tx = {
        "tx_hash": "ab" * 32, "block_number": 9, "gas_used": 60_000,
        "effective_gas_price_wei": 2_000_000_000,
        "contract_address": "0xC",
    }
    r = build_study_record("study1", "merkle_batch", cfg, tx,
                           file_count=10, merkle_root="0xROOT")
    check("T16 workflow stored", r.workflow == "merkle_batch")
    check("T17 network fields from config",
          r.network_key == "sepolia" and r.chain_id == 11155111)
    check("T18 total fee computed",
          r.total_fee_wei == 120_000_000_000_000)
    check("T19 cost per file amortised",
          r.cost_per_file_wei == 12_000_000_000_000)
    check("T20 tx hash 0x-prefixed", r.transaction_hash.startswith("0x"))
    check("T21 merkle root stored", r.merkle_root == "0xROOT")
    check("T22 native symbol from config", r.native_token_symbol == "ETH")


# ══════════════════════════════════════════════════════════════════
# 4. Full mocked gas study
# ══════════════════════════════════════════════════════════════════


def test_full_gas_study():
    section("Full Mocked Gas Study")
    import proof_client.gas_study as gs

    calls = []
    tmp = _tmp()
    with patch("proof_client.contract_client.register_hash",
               _fake_register_factory(calls)):
        study = gs.run_gas_study(network_key="anvil", batch_size=3,
                                 output_dir=tmp)

    check("T23 N+1 transactions for batch size N", len(calls) == 4)
    check("T24 study has 4 records", len(study["records"]) == 4)
    check("T25 study network is anvil", study["network_key"] == "anvil")
    check("T26 contract address recorded",
          study["contract_address"] == "0xSTUDYCONTRACT")
    check("T27 default workflows single_file + merkle_batch",
          study["workflows"] == ["single_file", "merkle_batch"])

    workflows = [r["workflow"] for r in study["records"]]
    check("T28 3 single_file records", workflows.count("single_file") == 3)
    check("T29 1 merkle_batch record", workflows.count("merkle_batch") == 1)

    merkle_rec = next(r for r in study["records"]
                      if r["workflow"] == "merkle_batch")
    check("T30 merkle record covers all files", merkle_rec["file_count"] == 3)
    check("T31 merkle record has root", merkle_rec["merkle_root"].startswith("0x"))

    sd = Path(study["study_dir"])
    for i, fname in enumerate(("gas_study.json", "gas_study.csv",
                               "transactions.json", "gas_study.md",
                               "gas_study_report.pdf", "README.md"), start=32):
        check(f"T{i} {fname} written", (sd / fname).exists())

    # Samples are salted per workflow → no duplicate hashes in one study
    hashes = [c["file_hash"] for c in calls]
    check("T38 no duplicate hashes within study",
          len(hashes) == len(set(hashes)))

    # CSV structure
    with (sd / "gas_study.csv").open() as f:
        rows = list(csv.DictReader(f))
    check("T39 CSV has one row per transaction", len(rows) == 4)
    check("T40 CSV columns match spec",
          set(rows[0].keys()) == set(gs.CSV_COLUMNS))
    check("T41 CSV records fee", rows[0]["total_fee_eth"] == "0.000072")

    # JSON structure
    data = json.loads((sd / "gas_study.json").read_text())
    check("T42 JSON study_id matches", data["study_id"] == study["study_id"])
    check("T43 JSON has salt", data["salt"] == study["study_id"])

    # Explicit salt is honoured
    calls2 = []
    with patch("proof_client.contract_client.register_hash",
               _fake_register_factory(calls2)):
        study2 = gs.run_gas_study(network_key="anvil", batch_size=2,
                                  output_dir=tmp, salt="fixed-salt")
    data2 = json.loads(
        (Path(study2["study_dir"]) / "gas_study.json").read_text())
    check("T44 explicit salt stored", data2["salt"] == "fixed-salt")


# ══════════════════════════════════════════════════════════════════
# 5. Workflow selection
# ══════════════════════════════════════════════════════════════════


def test_workflow_selection():
    section("Workflow Selection Flags")
    import proof_client.gas_study as gs

    tmp = _tmp()

    calls = []
    with patch("proof_client.contract_client.register_hash",
               _fake_register_factory(calls)):
        study = gs.run_gas_study(network_key="anvil", batch_size=2,
                                 output_dir=tmp, include_merkle=False)
    check("T45 --no-merkle skips batch experiment",
          study["workflows"] == ["single_file"] and len(calls) == 2)

    calls2 = []
    with patch("proof_client.contract_client.register_hash",
               _fake_register_factory(calls2)):
        study2 = gs.run_gas_study(network_key="anvil", batch_size=2,
                                  output_dir=tmp, include_ipfs=True,
                                  ipfs_provider="mock")
    check("T46 include_ipfs adds workflow", "ipfs" in study2["workflows"])
    check("T47 ipfs adds N transactions", len(calls2) == 5)
    ipfs_recs = [r for r in study2["records"] if r["workflow"] == "ipfs"]
    check("T48 ipfs records created", len(ipfs_recs) == 2)

    calls3 = []
    with patch("proof_client.contract_client.register_hash",
               _fake_register_factory(calls3)):
        study3 = gs.run_gas_study(network_key="anvil", batch_size=2,
                                  output_dir=tmp,
                                  include_encrypted_ipfs=True,
                                  ipfs_provider="mock")
    check("T49 include_encrypted_ipfs adds workflow",
          "encrypted_ipfs" in study3["workflows"])
    enc_recs = [r for r in study3["records"]
                if r["workflow"] == "encrypted_ipfs"]
    check("T50 encrypted_ipfs records created", len(enc_recs) == 2)


# ══════════════════════════════════════════════════════════════════
# 6. Dry run
# ══════════════════════════════════════════════════════════════════


def test_dry_run():
    section("Gas Study Dry Run")
    import proof_client.gas_study as gs

    tmp = _tmp()
    calls = []
    with patch("proof_client.contract_client.register_hash",
               _fake_register_factory(calls)):
        study = gs.run_gas_study(network_key="anvil", batch_size=5,
                                 output_dir=tmp, dry_run=True)

    check("T51 dry run broadcasts nothing", len(calls) == 0)
    check("T52 dry run flagged in study", study["dry_run"] is True)
    check("T53 dry run has no records", study["records"] == [])
    sd = Path(study["study_dir"])
    check("T54 dry run writes no gas_study.json",
          not (sd / "gas_study.json").exists())

    try:
        gs.run_gas_study(network_key="anvil", batch_size=0, output_dir=tmp)
        fail("T55 batch_size 0 raises", "did not raise")
    except ValueError:
        ok("T55 batch_size 0 raises")


# ══════════════════════════════════════════════════════════════════
# 7. Report aggregation
# ══════════════════════════════════════════════════════════════════


def _synthetic_study() -> dict:
    return {
        "study_id": "gas_study_synth", "network_key": "base_sepolia",
        "network_display_name": "Base Sepolia", "chain_id": 84532,
        "contract_address": "0xC", "native_token_symbol": "ETH",
        "batch_size": 5, "workflows": ["single_file", "merkle_batch"],
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


def test_report_aggregation():
    section("Report Aggregation")
    from proof_client.gas_report import compute_merkle_savings, summarize_workflows

    study = _synthetic_study()
    summaries = summarize_workflows(study["records"])

    single = summaries["single_file"]
    check("T56 single tx_count", single["tx_count"] == 5)
    check("T57 single file_count", single["file_count"] == 5)
    check("T58 single total gas", single["total_gas_used"] == 250_000)
    check("T59 single cost per file",
          single["cost_per_file_wei"] == 50_000 * 10**9)
    check("T60 single gas per file", single["gas_per_file"] == 50_000)

    merkle = summaries["merkle_batch"]
    check("T61 merkle tx_count", merkle["tx_count"] == 1)
    check("T62 merkle cost per file",
          merkle["cost_per_file_wei"] == 11_000 * 10**9)

    savings = compute_merkle_savings(summaries)
    check("T63 merkle savings computed", savings is not None)
    check("T64 savings = 78%", abs(savings - 78.0) < 0.01)

    check("T65 savings None without merkle",
          compute_merkle_savings({"single_file": single}) is None)
    check("T66 empty records → empty summaries",
          summarize_workflows([]) == {})


# ══════════════════════════════════════════════════════════════════
# 8. Markdown / PDF reports
# ══════════════════════════════════════════════════════════════════


def test_report_generation():
    section("Markdown / PDF Report Generation")
    from proof_client.gas_report import (
        build_markdown_report,
        generate_reports,
        load_study,
    )

    study = _synthetic_study()
    md = build_markdown_report(study)
    for i, expected in enumerate((
        "## 1. Study Overview", "## 2. Network Information",
        "## 3. Contract Information", "## 4. Cost per Workflow",
        "## 5. Cost Reduction Analysis", "## 6. Transaction Table",
        "## 7. Methodology", "## 8. Limitations",
    ), start=67):
        check(f"T{i} report has section {expected!r}", expected in md)

    check("T75 report names the network", "Base Sepolia" in md)
    check("T76 report shows savings", "saves 78.00% per file" in md)
    check("T77 report table lists both workflows",
          "| single_file |" in md and "| merkle_batch |" in md)

    tmp = _tmp()
    sd = tmp / "study"
    sd.mkdir()
    (sd / "gas_study.json").write_text(json.dumps(study))
    md_path, pdf_path = generate_reports(sd)
    check("T78 gas_study.md written", md_path.exists())
    check("T79 gas_study_report.pdf written",
          pdf_path is not None and pdf_path.exists())
    check("T80 PDF is a real PDF",
          pdf_path.read_bytes()[:5] == b"%PDF-")

    loaded = load_study(sd)
    check("T81 load_study round-trips", loaded["study_id"] == "gas_study_synth")

    try:
        load_study(tmp / "nope")
        fail("T82 missing study raises", "did not raise")
    except FileNotFoundError:
        ok("T82 missing study raises")


# ══════════════════════════════════════════════════════════════════
# 9. CLI
# ══════════════════════════════════════════════════════════════════


def test_cli():
    section("Gas Study CLI")
    from proof_client.gas_study import _parse_args, main

    args = _parse_args(["--network", "base-sepolia", "--batch-size", "10",
                        "--confirm"])
    check("T83 --network parsed", args.network == "base-sepolia")
    check("T84 --batch-size parsed", args.batch_size == 10)
    check("T85 --confirm parsed", args.confirm is True)
    check("T86 defaults: batch size 5",
          _parse_args(["--network", "anvil"]).batch_size == 5)

    args2 = _parse_args(["--network", "anvil", "--include-ipfs",
                         "--include-encrypted-ipfs", "--no-merkle",
                         "--dry-run", "--salt", "s1"])
    check("T87 all flags parsed",
          args2.include_ipfs and args2.include_encrypted_ipfs
          and args2.no_merkle and args2.dry_run and args2.salt == "s1")

    rc = main(["--network", "anvil"])
    check("T88 broadcast without --confirm refused", rc == 2)

    from proof_client.gas_report import _parse_args as rep_parse
    rargs = rep_parse(["--study", "reports/gas_studies/x"])
    check("T89 gas_report --study parsed",
          rargs.study == "reports/gas_studies/x")


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


def main_tests():
    print("=" * 60)
    print("  Stage 13 Test Suite — Gas Study & Reports")
    print("=" * 60)

    test_sample_generation()
    test_gas_study_record()
    test_build_study_record()
    test_full_gas_study()
    test_workflow_selection()
    test_dry_run()
    test_report_aggregation()
    test_report_generation()
    test_cli()

    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  Stage 13 Gas Study Results: {_passed}/{total} passed, {_failed} failed")
    print(f"{'=' * 60}\n")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main_tests()
