"""
gas_report.py — Markdown / PDF reports for gas studies (Stage 13)

Reads a gas_study.json produced by gas_study.py, aggregates the per-
transaction records into per-workflow summaries, computes the Merkle
savings percentage, and writes gas_study.md + gas_study_report.pdf.

CLI:
  python -m proof_client.gas_report --study reports/gas_studies/<study_id>
"""

import argparse
import json
import sys
from pathlib import Path

from web3 import Web3

from proof_client.gas_cost import merkle_savings_percentage


# ── Aggregation ───────────────────────────────────────────────────


def summarize_workflows(records: list[dict]) -> dict[str, dict]:
    """Aggregate per-transaction records into one summary per workflow.

    Returns a dict keyed by workflow name with:
      tx_count, file_count, total_gas_used, total_fee_wei, total_fee_eth,
      cost_per_file_wei, cost_per_file_eth, gas_per_file
    """
    summaries: dict[str, dict] = {}
    for r in records:
        wf = r.get("workflow", "unknown")
        s = summaries.setdefault(wf, {
            "workflow": wf,
            "tx_count": 0,
            "file_count": 0,
            "total_gas_used": 0,
            "total_fee_wei": 0,
        })
        s["tx_count"] += 1
        s["file_count"] += r.get("file_count", 1)
        s["total_gas_used"] += r.get("gas_used", 0)
        s["total_fee_wei"] += r.get("total_fee_wei", 0)

    for s in summaries.values():
        files = max(s["file_count"], 1)
        s["total_fee_eth"] = str(Web3.from_wei(s["total_fee_wei"], "ether"))
        s["cost_per_file_wei"] = s["total_fee_wei"] // files
        s["cost_per_file_eth"] = str(Web3.from_wei(s["cost_per_file_wei"], "ether"))
        s["gas_per_file"] = s["total_gas_used"] // files
    return summaries


def compute_merkle_savings(summaries: dict[str, dict]) -> float | None:
    """Return the Merkle-vs-single-file savings percentage, or None."""
    single = summaries.get("single_file")
    merkle = summaries.get("merkle_batch")
    if not single or not merkle:
        return None
    return merkle_savings_percentage(
        single["cost_per_file_wei"], merkle["cost_per_file_wei"]
    )


# ── Markdown report ───────────────────────────────────────────────


def build_markdown_report(study: dict) -> str:
    """Render the full Markdown gas study report."""
    records = study.get("records", [])
    summaries = summarize_workflows(records)
    savings = compute_merkle_savings(summaries)
    symbol = study.get("native_token_symbol", "ETH")

    lines = [
        f"# Gas Cost Study — {study.get('study_id', '')}",
        "",
        "## 1. Study Overview",
        "",
        f"- **Study ID:** `{study.get('study_id', '')}`",
        f"- **Created:** {study.get('created_at_utc', '')}",
        f"- **Batch size:** {study.get('batch_size', 0)}",
        f"- **Workflows:** {', '.join(study.get('workflows', []))}",
        f"- **Transactions measured:** {len(records)}",
        "",
        "## 2. Network Information",
        "",
        f"- **Network:** {study.get('network_display_name', '')}",
        f"- **Network key:** `{study.get('network_key', '')}`",
        f"- **Chain ID:** {study.get('chain_id', '')}",
        f"- **Native token:** {symbol}",
        "",
        "## 3. Contract Information",
        "",
        f"- **Contract address:** `{study.get('contract_address', '')}`",
        "",
        "## 4. Cost per Workflow",
        "",
        "| Workflow | Files | Txs | Total gas | Gas / file | "
        f"Total fee ({symbol}) | Cost / file ({symbol}) |",
        "|----------|-------|-----|-----------|------------|-----------|------------|",
    ]
    for wf in ("deployment", "single_file", "ipfs", "encrypted_ipfs", "merkle_batch"):
        s = summaries.get(wf)
        if not s:
            continue
        lines.append(
            f"| {wf} | {s['file_count']} | {s['tx_count']} | "
            f"{s['total_gas_used']} | {s['gas_per_file']} | "
            f"{s['total_fee_eth']} | {s['cost_per_file_eth']} |"
        )

    lines += ["", "## 5. Cost Reduction Analysis", ""]
    if savings is not None:
        single = summaries["single_file"]
        merkle = summaries["merkle_batch"]
        lines += [
            f"- Single-file cost per file: **{single['cost_per_file_eth']} {symbol}** "
            f"({single['tx_count']} transactions for {single['file_count']} files)",
            f"- Merkle batch cost per file: **{merkle['cost_per_file_eth']} {symbol}** "
            f"(1 transaction for {merkle['file_count']} files)",
            f"- **Merkle batching saves {savings:.2f}% per file** at this batch size.",
            "",
            "The saving grows with batch size: the batch pays for one fixed-cost",
            "transaction regardless of how many file hashes the Merkle root covers.",
        ]
    else:
        lines.append("_Both single_file and merkle_batch workflows are required "
                     "for a savings comparison._")

    lines += [
        "",
        "## 6. Transaction Table",
        "",
        "| Workflow | Tx hash | Block | Gas used | Fee (" + symbol + ") | Files |",
        "|----------|---------|-------|----------|----------|-------|",
    ]
    for r in records:
        tx = r.get("transaction_hash", "")
        tx_short = f"{tx[:12]}…" if len(tx) > 12 else tx
        lines.append(
            f"| {r.get('workflow', '')} | `{tx_short}` | {r.get('block_number', 0)} | "
            f"{r.get('gas_used', 0)} | {r.get('total_fee_eth', '')} | "
            f"{r.get('file_count', 1)} |"
        )

    lines += [
        "",
        "## 7. Methodology",
        "",
        "- Sample files are generated deterministically (fixed content per index",
        "  and salt) so experiments are reproducible.",
        "- Each study salts its samples with the study ID because the contract",
        "  rejects re-registration of an already-registered hash.",
        "- `single_file` registers each file hash in its own transaction;",
        "  `merkle_batch` registers one Merkle root covering all files.",
        "- Costs use the receipt's `gasUsed × effectiveGasPrice`.",
        "",
        "## 8. Limitations",
        "",
        "- Gas prices fluctuate; absolute fees are a snapshot, not a forecast.",
        "- Testnet gas prices do not reflect mainnet or L2 mainnet pricing.",
        "- IPFS upload costs (pinning, storage) are off-chain and not measured.",
        "- Merkle batching amortises the transaction fee but requires keeping",
        "  per-file proofs to remain verifiable.",
        "",
        "---",
        "",
        "*Generated by proof_client gas_report*",
        "",
    ]
    return "\n".join(lines)


# ── PDF report ────────────────────────────────────────────────────


def generate_pdf_report(study: dict, out_path: Path) -> Path | None:
    """Write a simple PDF version of the report; None if reportlab is missing."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError:
        return None

    records = study.get("records", [])
    summaries = summarize_workflows(records)
    savings = compute_merkle_savings(summaries)
    symbol = study.get("native_token_symbol", "ETH")

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    story = [
        Paragraph(f"Gas Cost Study — {study.get('study_id', '')}", styles["Title"]),
        Spacer(1, 6),
        Paragraph(
            f"Network: {study.get('network_display_name', '')} "
            f"(chain ID {study.get('chain_id', '')}) — "
            f"Contract: {study.get('contract_address', '')}",
            styles["Normal"],
        ),
        Spacer(1, 12),
        Paragraph("Cost per Workflow", styles["Heading2"]),
    ]

    table_data = [[
        "Workflow", "Files", "Txs", "Total gas",
        f"Total fee ({symbol})", f"Cost/file ({symbol})",
    ]]
    for wf in ("deployment", "single_file", "ipfs", "encrypted_ipfs", "merkle_batch"):
        s = summaries.get(wf)
        if not s:
            continue
        table_data.append([
            wf, str(s["file_count"]), str(s["tx_count"]),
            str(s["total_gas_used"]), s["total_fee_eth"], s["cost_per_file_eth"],
        ])
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A3A5C")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F5F5F5")]),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    if savings is not None:
        story.append(Paragraph("Cost Reduction Analysis", styles["Heading2"]))
        story.append(Paragraph(
            f"Merkle batching saves {savings:.2f}% per file compared with "
            f"single-file registration at batch size "
            f"{summaries['merkle_batch']['file_count']}.",
            styles["Normal"],
        ))

    doc.build(story)
    return out_path


# ── Entry points ──────────────────────────────────────────────────


def load_study(study_dir: Path) -> dict:
    """Load gas_study.json from a study directory."""
    path = study_dir / "gas_study.json"
    if not path.exists():
        raise FileNotFoundError(f"gas_study.json not found in {study_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def generate_reports(study_dir: Path) -> tuple[Path, Path | None]:
    """Generate gas_study.md and gas_study_report.pdf for a study directory."""
    study = load_study(study_dir)
    md_path = study_dir / "gas_study.md"
    md_path.write_text(build_markdown_report(study), encoding="utf-8")
    pdf_path = generate_pdf_report(study, study_dir / "gas_study_report.pdf")
    return md_path, pdf_path


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.gas_report",
        description="Generate Markdown/PDF reports from a gas study directory.",
    )
    parser.add_argument("--study", required=True,
                        help="Path to the study directory containing gas_study.json")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    try:
        md, pdf = generate_reports(Path(args.study))
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Markdown report: {md}")
    if pdf:
        print(f"PDF report:      {pdf}")
