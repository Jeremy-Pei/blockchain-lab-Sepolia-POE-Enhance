"""
evidence_store.py — 证据 JSON 文件持久化

将 EvidenceRecord 保存为 evidence/evidence_<hash前8位>.json 文件，
并支持加载已有的证据文件。
"""

import json
from pathlib import Path

from proof_client.config import EVIDENCE_DIR
from proof_client.evidence_schema import EvidenceRecord


def _evidence_filename(file_hash: str) -> str:
    """根据文件哈希生成证据文件名。"""
    short = file_hash.replace("0x", "")[:8]
    return f"evidence_{short}.json"


def save_evidence(record: EvidenceRecord) -> Path:
    """
    将证据记录保存为 JSON 文件。

    Args:
        record: EvidenceRecord 实例。

    Returns:
        保存的文件路径。
    """
    filename = _evidence_filename(record.file_hash)
    path = EVIDENCE_DIR / filename

    with open(path, "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"✅ 证据已保存: {path}")
    return path


def load_evidence(file_hash: str) -> EvidenceRecord | None:
    """
    根据文件哈希加载证据 JSON 文件。

    Args:
        file_hash: 0x 前缀的 SHA-256 哈希。

    Returns:
        EvidenceRecord 实例，如果文件不存在则返回 None。
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
    加载 evidence/ 目录下的所有证据文件。

    Returns:
        EvidenceRecord 列表，按文件名排序。
    """
    records = []
    for path in sorted(EVIDENCE_DIR.glob("evidence_*.json")):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        records.append(EvidenceRecord.from_dict(data))
    return records
