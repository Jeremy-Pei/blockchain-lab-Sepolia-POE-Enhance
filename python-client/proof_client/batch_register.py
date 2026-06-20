"""
batch_register.py — 批量注册文件

扫描 works/ 目录下的所有文件，逐一注册到链上。
"""

import sys
from pathlib import Path

from proof_client.config import WORKS_DIR
from proof_client.register_file import register_file
from proof_client.evidence_schema import EvidenceRecord


def batch_register(
    directory: str | Path | None = None,
    pattern: str = "*",
) -> list[EvidenceRecord]:
    """
    批量注册目录下的所有文件。

    Args:
        directory: 要扫描的目录，默认为 works/。
        pattern: glob 匹配模式，默认 '*' 匹配所有文件。

    Returns:
        成功注册的 EvidenceRecord 列表。
    """
    dir_path = Path(directory) if directory else WORKS_DIR

    if not dir_path.exists():
        print(f"❌ 目录不存在: {dir_path}")
        return []

    # 收集文件（排除隐藏文件和目录）
    files = sorted(
        f for f in dir_path.glob(pattern)
        if f.is_file() and not f.name.startswith(".")
    )

    if not files:
        print(f"⚠️  目录 {dir_path} 下没有找到匹配的文件。")
        return []

    print(f"📂 找到 {len(files)} 个文件待注册:")
    for i, f in enumerate(files, 1):
        print(f"   {i}. {f.name}")
    print()

    results: list[EvidenceRecord] = []
    failed: list[tuple[str, str]] = []

    for i, f in enumerate(files, 1):
        print(f"{'='*60}")
        print(f"[{i}/{len(files)}] 正在注册: {f.name}")
        print(f"{'='*60}")
        try:
            record = register_file(str(f))
            results.append(record)
        except Exception as e:
            print(f"❌ 注册失败: {e}")
            failed.append((f.name, str(e)))
        print()

    # 汇总
    print(f"{'='*60}")
    print(f"📊 批量注册完成")
    print(f"   成功: {len(results)}")
    print(f"   失败: {len(failed)}")
    if failed:
        print(f"   失败文件:")
        for name, err in failed:
            print(f"     - {name}: {err}")

    return results


# ── CLI 入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else None
    batch_register(directory)
