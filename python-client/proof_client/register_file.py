"""
register_file.py — 注册文件到链上

完整流程：计算哈希 → 调用合约 register → 保存证据（JSON + SQLite）。
"""

import sys
from pathlib import Path

from proof_client.config import CONTRACT_ADDRESS, EXPLORER_TX_URL
from proof_client.hash_file import sha256_hash
from proof_client.wallet import get_address
from proof_client.contract_client import register_hash
from proof_client.evidence_schema import EvidenceRecord
from proof_client.evidence_store import save_evidence
from proof_client import evidence_repository as repo


def register_file(file_path: str, uri: str | None = None) -> EvidenceRecord:
    """
    注册单个文件到区块链。

    Args:
        file_path: 文件路径。
        uri: 可选的文件标识符，默认使用 sepolia://<filename>。

    Returns:
        EvidenceRecord 实例。
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    file_name = path.name
    if uri is None:
        uri = f"sepolia://{file_name}"

    # 1) 计算哈希
    file_hash = sha256_hash(path)
    print(f"📄 文件: {file_name}")
    print(f"🔑 SHA-256: {file_hash}")

    # 2) 调用合约
    print("⏳ 正在提交到 Sepolia 链上...")
    result = register_hash(file_hash, uri)
    print("✅ 交易成功!")
    print(f"   Tx Hash: 0x{result['tx_hash']}")
    print(f"   Block:   {result['block_number']}")
    print(f"   Gas:     {result['gas_used']}")

    # 3) 组装证据记录
    record = EvidenceRecord(
        file_name=file_name,
        file_hash=file_hash,
        uri=uri,
        tx_hash=result["tx_hash"],
        block_number=result["block_number"],
        gas_used=result["gas_used"],
        owner=get_address(),
        status=result["status"],
        contract_address=CONTRACT_ADDRESS,
        explorer_tx_url=EXPLORER_TX_URL,
    )

    # 4) 双写持久化：JSON + SQLite
    save_evidence(record)
    repo.insert(record)

    print(f"🔗 浏览器查看: {record.explorer_link}")
    return record


# ── CLI 入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m proof_client.register_file <文件路径> [uri]")
        sys.exit(1)

    fpath = sys.argv[1]
    file_uri = sys.argv[2] if len(sys.argv) > 2 else None
    register_file(fpath, file_uri)
