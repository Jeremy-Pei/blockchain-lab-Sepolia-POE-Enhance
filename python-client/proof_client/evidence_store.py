"""
evidence_store.py — Evidence JSON file persistence

Saves EvidenceRecord objects as evidence/evidence_<hash8>.json files
and supports loading existing evidence files.
"""

import json
from pathlib import Path

from proof_client.config import EVIDENCE_DIR
from proof_client.evidence_schema import EvidenceRecord


def _evidence_filename(file_hash: str) -> str:
    """Generate an evidence filename from a file hash."""
    short = file_hash.replace("0x", "")[:8]
    return f"evidence_{short}.json"


def save_evidence(record: EvidenceRecord) -> Path:
    """
    Save an evidence record as a JSON file.

    Args:
        record: EvidenceRecord instance.

    Returns:
        Path to the saved file.
    """
    filename = _evidence_filename(record.file_hash)
    path = EVIDENCE_DIR / filename

    with open(path, "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"✅ Evidence saved: {path}")
    return path


def load_evidence(file_hash: str) -> EvidenceRecord | None:
    """
    Load an evidence JSON file by file hash.

    Args:
        file_hash: 0x-prefixed SHA-256 hash.

    Returns:
        EvidenceRecord instance, or None if the file does not exist.
    """
    filename = _evidence_filename(file_hash)
    path = EVIDENCE_DIR / filename

    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return EvidenceRecord.from_dict(data)


def list_all_evidence() -> list[EvidenceRecord]:
    """
    Load all evidence files from the evidence/ directory.

    Returns:
        List of EvidenceRecord instances sorted by filename.
    """
    records = []
    for path in sorted(EVIDENCE_DIR.glob("evidence_*.json")):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        records.append(EvidenceRecord.from_dict(data))
    return records
