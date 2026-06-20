"""
hash_file.py — 计算文件的 SHA-256 哈希

将文件内容读取后计算 SHA-256 摘要，返回 0x 前缀的十六进制字符串，
与 Solidity 合约中使用的 bytes32 格式一致。
"""

import hashlib
import sys
from pathlib import Path


def sha256_hash(file_path: str | Path) -> str:
    """
    计算文件的 SHA-256 哈希值。

    Args:
        file_path: 要计算哈希的文件路径。

    Returns:
        带 0x 前缀的 64 字符十六进制哈希字符串。

    Raises:
        FileNotFoundError: 如果文件不存在。
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)

    return "0x" + h.hexdigest()


# ── CLI 入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m proof_client.hash_file <文件路径>")
        sys.exit(1)

    target = sys.argv[1]
    digest = sha256_hash(target)
    print(f"文件: {target}")
    print(f"SHA-256: {digest}")
