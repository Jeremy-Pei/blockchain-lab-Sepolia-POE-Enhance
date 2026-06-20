"""
verify_file.py — 验证文件是否已链上注册

完整流程：计算哈希 → 调用合约 verify → 比对本地证据。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from proof_client.hash_file import sha256_hash
from proof_client.contract_client import verify_hash
from proof_client.evidence_store import load_evidence


def verify_file(file_path: str) -> dict:
    """
    验证文件是否已在链上注册。

    Args:
        file_path: 文件路径。

    Returns:
        包含验证结果的字典：
        - registered: 是否已注册
        - file_hash: 文件哈希
        - chain_data: 链上数据 (owner, timestamp, uri)
        - local_evidence: 本地证据记录（如果有）
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    # 1) 计算当前文件哈希
    file_hash = sha256_hash(path)
    print(f"📄 文件: {path.name}")
    print(f"🔑 SHA-256: {file_hash}")

    # 2) 查询链上记录
    print("🔍 查询链上记录...")
    chain_data = verify_hash(file_hash)

    if not chain_data["registered"]:
        print("❌ 该文件哈希尚未在链上注册。")
        return {
            "registered": False,
            "file_hash": file_hash,
            "chain_data": chain_data,
            "local_evidence": None,
        }

    # 3) 显示链上信息
    ts = chain_data["timestamp"]
    ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    print("✅ 文件已在链上注册!")
    print(f"   Owner:     {chain_data['owner']}")
    print(f"   Timestamp: {ts} ({ts_str})")
    print(f"   URI:       {chain_data['uri']}")

    # 4) 尝试加载本地证据
    local = load_evidence(file_hash)
    if local:
        print(f"📋 本地证据记录: 已找到 (Tx: 0x{local.tx_hash[:16]}...)")
    else:
        print("📋 本地证据记录: 未找到")

    return {
        "registered": True,
        "file_hash": file_hash,
        "chain_data": chain_data,
        "local_evidence": local,
    }


# ── CLI 入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m proof_client.verify_file <文件路径>")
        sys.exit(1)

    verify_file(sys.argv[1])
