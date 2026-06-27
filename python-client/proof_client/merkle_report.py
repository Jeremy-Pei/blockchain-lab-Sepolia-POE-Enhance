"""
merkle_report.py — Batch Merkle certificate generation (Markdown + PDF)

Generates:
  reports/batches/<batch_id>_certificate.md
  reports/batches/<batch_id>_certificate.pdf
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

from proof_client.config import BATCH_REPORTS_DIR
from proof_client.merkle_evidence import BatchEvidence, MerkleLeaf


# ── Colour palette (matches single-file pdf_report.py) ───────────
_DARK_BLUE  = colors.HexColor("#1A3A5C")
_MID_BLUE   = colors.HexColor("#2E6DA4")
_LIGHT_GREY = colors.HexColor("#F5F5F5")
_BORDER     = colors.HexColor("#CCCCCC")


# ── Markdown certificate ──────────────────────────────────────────

_MAX_FILES_TABLE = 20


def build_batch_markdown_certificate(evidence: BatchEvidence, leaves: list[MerkleLeaf]) -> str:
    """Return the full Markdown text of the batch certificate."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    tx = evidence.transaction_hash or ""
    if tx and not tx.startswith("0x"):
        tx = "0x" + tx

    # Files table
    shown = leaves[:_MAX_FILES_TABLE]
    rows = "\n".join(
        f"| {lf.index} | `{lf.relative_path}` | `{lf.file_hash}` | `{lf.relative_path}.proof.json` |"
        for lf in shown
    )
    overflow_note = ""
    if len(leaves) > _MAX_FILES_TABLE:
        overflow_note = f"\n*{len(leaves) - _MAX_FILES_TABLE} more files omitted. See `leaves.json` for the complete file list.*\n"

    return f"""# Batch Proof-of-Existence Certificate

> This certificate records the Merkle root of a batch of files registered on the
> {evidence.network} blockchain. A Merkle proof proves that a file hash was
> included in this registered batch root. It does not by itself prove authorship
> or legal ownership.

---

## 1. Batch Summary

| Field | Value |
|-------|-------|
| **Batch ID** | `{evidence.batch_id}` |
| **Batch title** | {evidence.batch_title or "—"} |
| **Author** | {evidence.author or "—"} |
| **Description** | {evidence.description or "—"} |
| **File count** | {evidence.file_count} |
| **Merkle root** | `{evidence.merkle_root}` |
| **URI** | `{evidence.uri}` |
| **Created at** | {evidence.created_at_utc} |

---

## 2. Included Files

| # | Relative path | File SHA-256 | Proof file |
|---|---------------|--------------|------------|
{rows}
{overflow_note}
---

## 3. Merkle Tree Rules

| Parameter | Value |
|-----------|-------|
| **Leaf hash algorithm** | {evidence.leaf_hash_algorithm} of file bytes |
| **Internal node algorithm** | {evidence.merkle_algorithm} |
| **Leaf ordering** | {evidence.leaf_ordering} |
| **Odd-leaf strategy** | {evidence.odd_leaf_strategy} |

---

## 4. Merkle Root Registration

The Merkle root was registered on-chain using the standard
`register(bytes32 fileHash, string uri)` function.

| Field | Value |
|-------|-------|
| **Registered as** | `fileHash` parameter (Merkle root, not a single file hash) |
| **URI parameter** | `{evidence.uri}` |

---

## 5. Blockchain Record

| Field | Value |
|-------|-------|
| **Network** | {evidence.network} (Chain ID {evidence.chain_id}) |
| **Contract address** | `{evidence.contract_address}` |
| **Transaction hash** | `{tx}` |
| **Block number** | {evidence.block_number} |
| **Block timestamp** | {evidence.block_timestamp} |
| **Owner address** | `{evidence.owner_address}` |
| **Explorer URL** | {evidence.explorer_url or "—"} |

---

## 6. Per-File Proofs

Each file in this batch has a corresponding `.proof.json` file in the
`proofs/` directory. The proof contains the sibling hashes and positions needed
to recompute the Merkle root from the file's SHA-256 alone.

---

## 7. Verification Method

To verify that a file belongs to this registered batch:

```bash
# Step 1: Recompute the file's SHA-256.
shasum -a 256 <your_file>

# Step 2: Load the corresponding proof JSON.
# Step 3: Recompute the Merkle root using the proof.
# Step 4: Compare with the registered merkle_root above.
# Step 5: Query the blockchain to confirm the root is on-chain.

python -m proof_client.verify_merkle_proof \\
    --file <your_file> \\
    --proof proofs/<file>.proof.json \\
    --chain
```

---

## 8. Limitations

- A Merkle proof verifies that a file hash was included in a registered batch
  root. It does not prove legal authorship, copyright ownership, or originality.
- If the proof file is lost, the file can still be verified by re-building the
  Merkle tree from `leaves.json` and `merkle_tree.json`.

---

## 9. Declaration

This certificate was generated automatically by `proof_client`. The Merkle root
recorded on {evidence.network} is immutable and cannot be altered retroactively.

---

*Certificate generated at: {now}*
"""


def generate_batch_markdown_certificate(
    evidence: BatchEvidence,
    leaves: list[MerkleLeaf],
    output_dir: Optional[Path] = None,
) -> Path:
    """Write the batch Markdown certificate and return its path."""
    out = output_dir or BATCH_REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{evidence.batch_id}_certificate.md"
    path.write_text(
        build_batch_markdown_certificate(evidence, leaves), encoding="utf-8"
    )
    return path


# ── PDF certificate ───────────────────────────────────────────────


def _pdf_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "batch_title", parent=base["Heading1"],
            fontSize=16, textColor=_DARK_BLUE, spaceAfter=4, leading=20,
        ),
        "subtitle": ParagraphStyle(
            "batch_subtitle", parent=base["Normal"],
            fontSize=9, textColor=colors.grey, spaceAfter=10,
        ),
        "section": ParagraphStyle(
            "batch_section", parent=base["Heading2"],
            fontSize=11, textColor=_MID_BLUE, spaceBefore=12, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "batch_body", parent=base["Normal"],
            fontSize=9, leading=13, spaceAfter=3,
        ),
        "mono": ParagraphStyle(
            "batch_mono", parent=base["Code"],
            fontSize=7, leading=10, spaceAfter=3,
            fontName="Courier",
        ),
        "warning": ParagraphStyle(
            "batch_warning", parent=base["Normal"],
            fontSize=8, textColor=colors.HexColor("#CC3300"), leading=12,
        ),
    }


def _table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _DARK_BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("FONTSIZE",   (0, 1), (-1, -1), 7),
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_LIGHT_GREY, colors.white]),
        ("GRID",       (0, 0), (-1, -1), 0.3, _BORDER),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("WORDWRAP",   (0, 0), (-1, -1), True),
    ])


def generate_batch_pdf_certificate(
    evidence: BatchEvidence,
    leaves: list[MerkleLeaf],
    output_dir: Optional[Path] = None,
) -> Path:
    """Generate the batch PDF certificate and return its path."""
    out = output_dir or BATCH_REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    pdf_path = out / f"{evidence.batch_id}_certificate.pdf"

    s = _pdf_styles()
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    tx = evidence.transaction_hash or ""
    if tx and not tx.startswith("0x"):
        tx = "0x" + tx

    story = []

    # Title
    story.append(Paragraph("Batch Proof-of-Existence Certificate", s["title"]))
    story.append(Paragraph(f"Generated at: {now} · {evidence.network}", s["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=_DARK_BLUE, spaceAfter=8))

    # Batch summary
    story.append(Paragraph("1. Batch Summary", s["section"]))
    summary_data = [
        ["Field", "Value"],
        ["Batch ID", evidence.batch_id],
        ["Batch title", evidence.batch_title or "—"],
        ["Author", evidence.author or "—"],
        ["File count", str(evidence.file_count)],
        ["Merkle root", evidence.merkle_root],
        ["URI", evidence.uri],
        ["Created at", evidence.created_at_utc],
    ]
    t = Table(summary_data, colWidths=[45 * mm, 130 * mm])
    t.setStyle(_table_style())
    story.append(t)
    story.append(Spacer(1, 8))

    # Included files
    story.append(Paragraph("2. Included Files", s["section"]))
    shown = leaves[:_MAX_FILES_TABLE]
    files_data = [["#", "Relative path", "File SHA-256"]]
    for lf in shown:
        files_data.append([str(lf.index), lf.relative_path, lf.file_hash])
    t2 = Table(files_data, colWidths=[10 * mm, 65 * mm, 100 * mm])
    t2.setStyle(_table_style())
    story.append(t2)
    if len(leaves) > _MAX_FILES_TABLE:
        story.append(Paragraph(
            f"… {len(leaves) - _MAX_FILES_TABLE} more files. See leaves.json.",
            s["body"],
        ))
    story.append(Spacer(1, 6))

    # Merkle tree rules
    story.append(Paragraph("3. Merkle Tree Rules", s["section"]))
    rules_data = [
        ["Parameter", "Value"],
        ["Leaf hash algorithm", f"{evidence.leaf_hash_algorithm} of file bytes"],
        ["Internal node", evidence.merkle_algorithm],
        ["Leaf ordering", evidence.leaf_ordering],
        ["Odd-leaf strategy", evidence.odd_leaf_strategy],
    ]
    t3 = Table(rules_data, colWidths=[60 * mm, 115 * mm])
    t3.setStyle(_table_style())
    story.append(t3)
    story.append(Spacer(1, 6))

    # Blockchain record
    story.append(Paragraph("4. Blockchain Record", s["section"]))
    chain_data = [
        ["Field", "Value"],
        ["Network", f"{evidence.network} (Chain ID {evidence.chain_id})"],
        ["Contract address", evidence.contract_address],
        ["Transaction hash", tx],
        ["Block number", str(evidence.block_number)],
        ["Block timestamp", str(evidence.block_timestamp)],
        ["Owner address", evidence.owner_address],
    ]
    t4 = Table(chain_data, colWidths=[45 * mm, 130 * mm])
    t4.setStyle(_table_style())
    story.append(t4)
    story.append(Spacer(1, 6))

    # Limitation notice
    story.append(Paragraph("5. Limitations", s["section"]))
    story.append(Paragraph(
        "A Merkle proof verifies that a file hash was included in a registered "
        "batch root. It does not prove legal authorship, copyright ownership, "
        "or originality.",
        s["warning"],
    ))

    doc.build(story)
    return pdf_path
