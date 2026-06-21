"""
pdf_report.py — Generate PDF evidence certificates

Converts an EvidenceRecord into a professional-looking PDF using
reportlab. The content mirrors the Markdown certificate defined in
report_template.py.

CLI:
  python -m proof_client.pdf_report --hash <file_hash>
  python -m proof_client.pdf_report --all
"""

import sys
from pathlib import Path

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

from proof_client.config import REPORTS_DIR
from proof_client.evidence_schema import EvidenceRecord
from proof_client.evidence_store import load_evidence, list_all_evidence
from proof_client.report_template import build_certificate_data, LIMITATIONS_TEXT


# ── Colour palette ────────────────────────────────────────────────
_DARK_BLUE = colors.HexColor("#1A3A5C")
_MID_BLUE  = colors.HexColor("#2E6DA4")
_LIGHT_GREY = colors.HexColor("#F5F5F5")
_BORDER    = colors.HexColor("#CCCCCC")


def _styles() -> dict:
    """Build and return a dict of named ParagraphStyles."""
    base = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "cert_title",
            parent=base["Heading1"],
            fontSize=18,
            textColor=_DARK_BLUE,
            spaceAfter=4,
            leading=22,
        ),
        "subtitle": ParagraphStyle(
            "cert_subtitle",
            parent=base["Normal"],
            fontSize=10,
            textColor=colors.grey,
            spaceAfter=12,
        ),
        "section": ParagraphStyle(
            "cert_section",
            parent=base["Heading2"],
            fontSize=11,
            textColor=_MID_BLUE,
            spaceBefore=14,
            spaceAfter=4,
            leading=14,
        ),
        "body": ParagraphStyle(
            "cert_body",
            parent=base["Normal"],
            fontSize=9,
            leading=13,
            spaceAfter=4,
        ),
        "mono": ParagraphStyle(
            "cert_mono",
            parent=base["Code"],
            fontSize=7.5,
            leading=11,
            spaceAfter=4,
            backColor=_LIGHT_GREY,
            leftIndent=6,
            rightIndent=6,
        ),
        "warning": ParagraphStyle(
            "cert_warning",
            parent=base["Normal"],
            fontSize=8.5,
            textColor=colors.HexColor("#7B4F00"),
            backColor=colors.HexColor("#FFF8E1"),
            leftIndent=8,
            rightIndent=8,
            spaceBefore=4,
            spaceAfter=4,
            leading=13,
        ),
    }


def _kv_table(rows: list[tuple[str, str]]) -> Table:
    """Build a two-column key-value table."""
    data = [[Paragraph(f"<b>{k}</b>", _styles()["body"]),
             Paragraph(str(v), _styles()["body"])]
            for k, v in rows]

    t = Table(data, colWidths=[45 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), _LIGHT_GREY),
        ("GRID",       (0, 0), (-1, -1), 0.4, _BORDER),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("FONTSIZE",     (0, 0), (-1, -1), 8.5),
    ]))
    return t


def _build_story(record: EvidenceRecord, manifest_hash: str = "") -> list:
    """Build the reportlab story (list of Flowables) for the certificate."""
    s = _styles()
    d = build_certificate_data(record, manifest_hash)
    story = []

    # ── Title ────────────────────────────────────────────────────
    story.append(Paragraph("Proof of Existence", s["title"]))
    story.append(Paragraph("Evidence Certificate", s["title"]))
    story.append(Paragraph(
        f"Certificate ID: <b>{d['certificate_id']}</b> &nbsp;&nbsp; "
        f"Generated: {d['generated_at_utc']}",
        s["subtitle"],
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_MID_BLUE))

    # ── Section 1: Summary ───────────────────────────────────────
    story.append(Paragraph("1. Certificate Summary", s["section"]))
    story.append(Paragraph(
        f"This certificate confirms that the SHA-256 fingerprint of the work "
        f"described below was registered on the <b>{d['network']}</b> blockchain.",
        s["body"],
    ))

    # ── Section 2: Work Information ──────────────────────────────
    story.append(Paragraph("2. Work Information", s["section"]))
    story.append(_kv_table([
        ("File name", d["file_name"]),
        ("SHA-256 hash", d["file_hash"]),
        ("URI", d["uri"]),
    ]))

    # ── Section 3: File Fingerprint ──────────────────────────────
    story.append(Paragraph("3. File Fingerprint", s["section"]))
    story.append(Paragraph(d["file_hash"], s["mono"]))
    story.append(Paragraph(
        f'To verify: <font face="Courier" size="8">shasum -a 256 "{d["file_name"]}"</font>',
        s["body"],
    ))

    # ── Section 4: Blockchain Registration ───────────────────────
    story.append(Paragraph("4. Blockchain Registration", s["section"]))
    story.append(_kv_table([
        ("Owner address",    d["owner_address"]),
        ("Contract address", d["contract_address"]),
        ("Network",          d["network"]),
        ("Chain ID",         str(d["chain_id"])),
        ("Transaction hash", d["tx_hash"]),
        ("Block number",     str(d["block_number"])),
        ("Block timestamp",  d["block_timestamp"]),
        ("Explorer URL",     d["explorer_url"]),
    ]))

    # ── Section 5: Local Evidence Record ─────────────────────────
    story.append(Paragraph("5. Local Evidence Record", s["section"]))
    story.append(_kv_table([
        ("Evidence JSON filename", d["evidence_filename"]),
        ("Package manifest hash",  d["package_manifest_hash"]),
    ]))

    # ── Section 6: Verification Method ───────────────────────────
    story.append(Paragraph("6. Verification Method", s["section"]))
    story.append(Paragraph(
        "<b>Step 1</b> — Recompute the SHA-256 hash of the original file and "
        "confirm it matches the fingerprint above.",
        s["body"],
    ))
    story.append(Paragraph(
        "<b>Step 2</b> — Call <font face='Courier'>verify(fileHash)</font> on "
        f"contract <font face='Courier'>{d['contract_address']}</font>. "
        f"The returned owner must be <font face='Courier'>{d['owner_address']}</font>.",
        s["body"],
    ))
    story.append(Paragraph(
        "<b>Step 3</b> — Run "
        "<font face='Courier'>python -m proof_client.verify_package &lt;package.zip&gt;</font> "
        "to confirm the evidence package has not been tampered with.",
        s["body"],
    ))

    # ── Section 7: Limitations ───────────────────────────────────
    story.append(Paragraph("7. Limitations", s["section"]))
    story.append(Paragraph(LIMITATIONS_TEXT, s["warning"]))

    # ── Section 8: Declaration ───────────────────────────────────
    story.append(Paragraph("8. Declaration", s["section"]))
    story.append(Paragraph(d["declaration"], s["body"]))

    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_BORDER))
    story.append(Paragraph(
        f"Certificate generated by proof_client · {d['generated_at_utc']}",
        s["subtitle"],
    ))

    return story


def generate_pdf(record: EvidenceRecord, manifest_hash: str = "") -> Path:
    """
    Generate a PDF evidence certificate for the given record.

    Args:
        record: EvidenceRecord to certify.
        manifest_hash: Optional SHA-256 of the package manifest.

    Returns:
        Path to the generated PDF file.
    """
    short = record.file_hash.replace("0x", "")[:8]
    filename = f"proof_report_{short}.pdf"
    path = REPORTS_DIR / filename

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Proof of Existence Certificate – {short}",
        author="proof_client",
    )
    doc.build(_build_story(record, manifest_hash))

    print(f"📄 PDF generated: {path}")
    return path


def generate_pdf_by_hash(file_hash: str) -> Path | None:
    """Generate a PDF report for a given file hash."""
    record = load_evidence(file_hash)
    if record is None:
        print(f"❌ No evidence file found for hash {file_hash}.")
        return None
    return generate_pdf(record)


def generate_all_pdfs() -> list[Path]:
    """Generate PDF reports for all existing evidence records."""
    records = list_all_evidence()
    if not records:
        print("⚠️  No evidence records found.")
        return []
    paths = []
    for record in records:
        path = generate_pdf(record)
        paths.append(path)
    print(f"\n✅ Generated {len(paths)} PDF(s).")
    return paths


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m proof_client.pdf_report --hash <file_hash>")
        print("  python -m proof_client.pdf_report --all")
        sys.exit(1)

    if sys.argv[1] == "--all":
        generate_all_pdfs()
    elif sys.argv[1] == "--hash" and len(sys.argv) >= 3:
        generate_pdf_by_hash(sys.argv[2])
    else:
        generate_pdf_by_hash(sys.argv[1])
