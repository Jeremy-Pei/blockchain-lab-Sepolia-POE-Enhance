"""
config.py — 统一配置管理

从 .env 文件加载环境变量，并提供项目路径常量。
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# ── 项目路径 ──────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

ABI_DIR = PROJECT_ROOT / "abi"
WORKS_DIR = PROJECT_ROOT / "works"
EVIDENCE_DIR = PROJECT_ROOT / "evidence"
REPORTS_DIR = PROJECT_ROOT / "reports"
DB_PATH = PROJECT_ROOT / "evidence.db"

# 确保必要的目录存在
for d in (WORKS_DIR, EVIDENCE_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── 区块链配置 ────────────────────────────────────────────────────
RPC_URL = os.getenv("RPC_URL", "")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
CHAIN_ID = int(os.getenv("CHAIN_ID", "11155111"))
EXPLORER_TX_URL = os.getenv("EXPLORER_TX_URL", "https://sepolia.etherscan.io/tx/")

# ── 加载 ABI ──────────────────────────────────────────────────────
ABI_PATH = ABI_DIR / "ProofOfExistence.json"


def load_abi() -> list:
    """加载合约 ABI JSON。"""
    with open(ABI_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
