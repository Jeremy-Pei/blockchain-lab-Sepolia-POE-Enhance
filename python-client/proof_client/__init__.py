"""
proof_client — Proof-of-Existence Python 客户端工具包

模块:
    config              统一配置管理
    hash_file           SHA-256 文件哈希计算
    wallet              Web3 连接与钱包管理
    contract_client     合约调用（register / verify）
    evidence_schema     证据数据结构（dataclass）
    evidence_store      证据 JSON 文件持久化
    evidence_repository 证据 SQLite 数据库持久化
    register_file       注册文件到链上
    verify_file         验证文件链上注册状态
    batch_register      批量注册
    generate_report     生成 Markdown 存证报告
    query_evidence      查询证据记录
"""

__version__ = "0.1.0"
