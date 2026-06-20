"""
generate_report.py — Generate Markdown proof-of-existence reports

Formats evidence records into human-readable Markdown reports
and saves them to the reports/ directory.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from proof_client.config import REPORTS_DIR
from proof_client.evidence_schema import EvidenceRecord
from proof_client.evidence_store import load_evidence, list_all_evidence


def _format_report(record: EvidenceRecord) -> str:
    """Format a single evidence record as a Markdown report."""
    return f"""# Proof of Existence Report

> This report is generated automatically by proof_client to prove that a specific
> version of a file existed on the blockchain at a given point in time.

---

## File Information

| Field | Value |
|-------|-------|
| **File name** | `{record.file_name}` |
| **SHA-256 hash** | `{record.file_hash}` |
| **URI** | `{record.uri}` |

## Blockchain Information

| Field | Value |
|-------|-------|
| **Network** | {record.network} |
| **Contract address** | `{record.contract_address}` |
| **Transaction hash** | `0x{record.tx_hash}` |
| **Block number** | {record.block_number} |
| **Gas used** | {record.gas_used} |
| **Owner address** | `{record.owner}` |
| **Timestamp** | {record.timestamp} ({record.timestamp_utc}) |
| **Status** | {record.status} |

## Block Explorer

- [View transaction on Etherscan]({record.explorer_link})

## How to Verify

1. **Recompute the SHA-256 hash of the original file**
   ```bash
   shasum -a 256 {record.file_name}
   ```
   Confirm the hash matches `{record.file_hash}`. Even a single changed byte
   will produce a completely different hash.

2. **Query the on-chain record**
   Call `verify(fileHash)` on the deployed contract:
   - Contract address: `{record.contract_address}`
   - Argument: `{record.file_hash}`

3. **Compare the results**
   - The returned `owner` should be `{record.owner}`
   - The returned `timestamp` is the immutable block timestamp
   - The returned `uri` should be `{record.uri}`

If all outputs match this report, mathematical proof of the file's integrity
and temporal existence is firmly established.

---

{f"> **Note:** {record.note}" if record.note else ""}

*Report generated at: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}*
"""


def generate_report(file_hash: str) -> Path | None:
    """
    Generate a Markdown report for the given file hash.

    Args:
        file_hash: 0x-prefixed file hash.

    Returns:
        Path to the report file, or None if no evidence record exists.
    """
    record = load_evidence(file_hash)
    if record is None:
        print(f"❌ No evidence file found for hash {file_hash}.")
        return None

    content = _format_report(record)

    short_hash = file_hash.replace("0x", "")[:8]
    filename = f"proof_report_{short_hash}.md"
    path = REPORTS_DIR / filename

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"📝 Report generated: {path}")
    return path


def generate_all_reports() -> list[Path]:
    """Generate reports for all existing evidence records."""
    records = list_all_evidence()
    if not records:
        print("⚠️  No evidence records found.")
        return []

    paths = []
    for record in records:
        content = _format_report(record)
        short_hash = record.file_hash.replace("0x", "")[:8]
        filename = f"proof_report_{short_hash}.md"
        path = REPORTS_DIR / filename

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        paths.append(path)
        print(f"📝 {record.file_name} → {filename}")

    print(f"\n✅ Generated {len(paths)} report(s).")
    return paths


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m proof_client.generate_report <file_hash>  # single report")
        print("  python -m proof_client.generate_report --all        # all reports")
        sys.exit(1)

    if sys.argv[1] == "--all":
        generate_all_reports()
    else:
        generate_report(sys.argv[1])
