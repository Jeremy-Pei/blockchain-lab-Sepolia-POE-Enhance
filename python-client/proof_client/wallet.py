"""
wallet.py — 钱包与 Web3 连接管理

提供 Web3 实例化、账户加载和交易签名的基础设施。
"""

from web3 import Web3
from eth_account import Account
from proof_client.config import RPC_URL, PRIVATE_KEY, CHAIN_ID


def get_w3() -> Web3:
    """
    创建并返回一个已连接的 Web3 实例。

    Raises:
        ConnectionError: 如果无法连接到 RPC 节点。
    """
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        raise ConnectionError(f"无法连接到 RPC 节点: {RPC_URL}")
    return w3


def get_account() -> Account:
    """
    从私钥创建 eth_account.Account 对象。

    Returns:
        Account 对象，可用于签名交易。
    """
    return Account.from_key(PRIVATE_KEY)


def get_address() -> str:
    """返回当前钱包地址（checksum 格式）。"""
    return get_account().address


def get_chain_id() -> int:
    """返回配置的链 ID。"""
    return CHAIN_ID
