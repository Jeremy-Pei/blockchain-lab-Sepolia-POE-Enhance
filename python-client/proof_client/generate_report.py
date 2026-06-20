"""
generate_report.py — 生成 Markdown 格式的存证报告

将证据记录格式化为人类可读的 Markdown 报告，
保存到 reports/ 目录。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from proof_client.config import REPORTS_DIR
from proof_client.evidence_schema import EvidenceRecord
from proof_client.evidence_store import load_evidence, list_all_evidence


def _format_report(record: EvidenceRecord) -> str:
    """将单条证据格式化为 Markdown 报告。"""
    return f"""# Proof of Existence Report

> 此报告由 proof_client 自动生成，证明特定文件版本在区块链上的存在性。

---

## 📄 文件信息

| 项目 | 值 |
|------|-----|
| **文件名** | `{record.file_name}` |
| **SHA-256 哈希** | `{record.file_hash}` |
| **URI** | `{record.uri}` |

## ⛓️ 区块链信息

| 项目 | 值 |
|------|-----|
| **网络** | {record.network} |
| **合约地址** | `{record.contract_address}` |
| **交易哈希** | `0x{record.tx_hash}` |
| **区块号** | {record.block_number} |
| **Gas 消耗** | {record.gas_used} |
| **注册者地址** | `{record.owner}` |
| **时间戳** | {record.timestamp} ({record.timestamp_utc}) |
| **状态** | {record.status} |

## 🔗 区块浏览器

- [在 Etherscan 查看交易]({record.explorer_link})

## ✅ 验证方法

1. **重新计算文件的 SHA-256 哈希**
   ```bash
   shasum -a 256 {record.file_name}
   ```
   确认哈希值与 `{record.file_hash}` 一致。

2. **查询链上记录**
   调用合约 `verify(fileHash)` 方法：
   - 合约地址: `{record.contract_address}`
   - 参数: `{record.file_hash}`

3. **比对结果**
   - 返回的 `owner` 应为 `{record.owner}`
   - 返回的 `timestamp` 为不可篡改的区块时间戳
   - 返回的 `uri` 应为 `{record.uri}`

如果所有输出与本报告一致，则数学上证明了该文件在该时间点的完整性和存在性。

---

{f"> **备注:** {record.note}" if record.note else ""}

*报告生成时间: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}*
"""


def generate_report(file_hash: str) -> Path | None:
    """
    为指定哈希的证据生成 Markdown 报告。

    Args:
        file_hash: 0x 前缀的文件哈希。

    Returns:
        报告文件路径，如果证据不存在则返回 None。
    """
    record = load_evidence(file_hash)
    if record is None:
        print(f"❌ 未找到哈希 {file_hash} 对应的证据文件。")
        return None

    content = _format_report(record)

    short_hash = file_hash.replace("0x", "")[:8]
    filename = f"proof_report_{short_hash}.md"
    path = REPORTS_DIR / filename

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"📝 报告已生成: {path}")
    return path


def generate_all_reports() -> list[Path]:
    """为所有已有的证据记录生成报告。"""
    records = list_all_evidence()
    if not records:
        print("⚠️  没有找到任何证据记录。")
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

    print(f"\n✅ 共生成 {len(paths)} 份报告。")
    return paths


# ── CLI 入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m proof_client.generate_report <file_hash>  # 单个报告")
        print("  python -m proof_client.generate_report --all        # 所有报告")
        sys.exit(1)

    if sys.argv[1] == "--all":
        generate_all_reports()
    else:
        generate_report(sys.argv[1])
