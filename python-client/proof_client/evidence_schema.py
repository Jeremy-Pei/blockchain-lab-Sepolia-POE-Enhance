"""
evidence_schema.py — 证据数据结构定义

使用 dataclass 定义链上证据的标准化数据结构，
用于在模块间传递和序列化证据信息。
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class EvidenceRecord:
    """一条链上存证记录。"""

    # ── 文件信息 ──
    file_name: str
    file_hash: str
    uri: str

    # ── 区块链信息 ──
    tx_hash: str = ""
    block_number: int = 0
    gas_used: int = 0
    owner: str = ""
    timestamp: int = 0
    status: str = ""

    # ── 元数据 ──
    network: str = "Ethereum Sepolia"
    chain_id: int = 11155111
    contract_address: str = ""
    explorer_tx_url: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ── 可选备注 ──
    note: Optional[str] = None

    # ── 序列化 ──

    def to_dict(self) -> dict:
        """转为字典，用于 JSON 序列化。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceRecord":
        """从字典创建 EvidenceRecord，自动过滤无效键。"""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    # ── 便利属性 ──

    @property
    def timestamp_utc(self) -> str:
        """将 Unix 时间戳转为 UTC 可读字符串。"""
        if self.timestamp == 0:
            return "N/A"
        return datetime.fromtimestamp(
            self.timestamp, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")

    @property
    def explorer_link(self) -> str:
        """完整的区块浏览器交易链接。"""
        if not self.explorer_tx_url or not self.tx_hash:
            return ""
        tx = self.tx_hash if self.tx_hash.startswith("0x") else f"0x{self.tx_hash}"
        return f"{self.explorer_tx_url}{tx}"
