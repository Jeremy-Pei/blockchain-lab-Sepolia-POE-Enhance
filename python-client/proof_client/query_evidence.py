"""
query_evidence.py — 查询证据记录

提供 CLI 和 API 两种方式查询本地数据库中的证据记录。
"""

import sys

from proof_client import evidence_repository as repo


def query_by_hash(file_hash: str) -> None:
    """根据文件哈希查询并打印证据记录。"""
    record = repo.find_by_hash(file_hash)
    if record is None:
        print(f"❌ 未找到哈希 {file_hash} 的证据记录。")
        return

    _print_record(record)


def query_by_owner(owner: str) -> None:
    """根据 owner 地址查询并打印证据记录。"""
    records = repo.find_by_owner(owner)
    if not records:
        print(f"❌ 未找到 owner {owner} 的证据记录。")
        return

    print(f"📋 找到 {len(records)} 条记录:")
    print()
    for r in records:
        _print_record(r)
        print()


def query_all() -> None:
    """查询并打印所有证据记录。"""
    records = repo.find_all()
    total = repo.count()

    if not records:
        print("⚠️  数据库中没有证据记录。")
        return

    print(f"📋 共 {total} 条证据记录:")
    print()
    for r in records:
        _print_record(r)
        print()


def query_stats() -> None:
    """打印证据统计信息。"""
    total = repo.count()
    records = repo.find_all()

    print(f"📊 证据统计")
    print(f"   总记录数: {total}")

    if records:
        owners = set(r.owner for r in records)
        print(f"   独立地址数: {len(owners)}")

        success = sum(1 for r in records if r.status == "success")
        print(f"   成功注册: {success}")
        print(f"   注册失败: {total - success}")


def _print_record(record) -> None:
    """格式化打印单条证据记录。"""
    print(f"  📄 文件名:   {record.file_name}")
    print(f"  🔑 哈希:     {record.file_hash}")
    print(f"  🔗 Tx Hash:  0x{record.tx_hash}")
    print(f"  📦 Block:    {record.block_number}")
    print(f"  👤 Owner:    {record.owner}")
    print(f"  ⏰ 时间:     {record.timestamp_utc}")
    print(f"  📌 状态:     {record.status}")


# ── CLI 入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m proof_client.query_evidence --all              # 所有记录")
        print("  python -m proof_client.query_evidence --hash <file_hash> # 按哈希查询")
        print("  python -m proof_client.query_evidence --owner <address>  # 按地址查询")
        print("  python -m proof_client.query_evidence --stats            # 统计信息")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "--all":
        query_all()
    elif cmd == "--hash" and len(sys.argv) > 2:
        query_by_hash(sys.argv[2])
    elif cmd == "--owner" and len(sys.argv) > 2:
        query_by_owner(sys.argv[2])
    elif cmd == "--stats":
        query_stats()
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
