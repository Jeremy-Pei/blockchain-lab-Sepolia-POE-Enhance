"""
contract_client.py — ProofOfExistence 合约交互客户端

封装 register / verify 两个核心合约方法，
处理交易构建、签名、发送和回执等待。
"""

from web3 import Web3
from web3.contract import Contract

from proof_client.config import CONTRACT_ADDRESS, load_abi
from proof_client.wallet import get_w3, get_account, get_chain_id


def _get_contract() -> tuple[Web3, Contract]:
    """返回 (w3, contract) 元组。"""
    w3 = get_w3()
    abi = load_abi()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(CONTRACT_ADDRESS),
        abi=abi,
    )
    return w3, contract


def register_hash(file_hash: str, uri: str) -> dict:
    """
    调用合约的 register(fileHash, uri) 方法。

    Args:
        file_hash: 0x 前缀的 SHA-256 文件哈希。
        uri: 文件标识符 / 路径。

    Returns:
        包含 tx_hash, block_number, gas_used, status 的字典。
    """
    w3, contract = _get_contract()
    account = get_account()

    # 将十六进制字符串转为 bytes32
    hash_bytes = bytes.fromhex(file_hash.replace("0x", ""))

    tx = contract.functions.register(hash_bytes, uri).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": get_chain_id(),
        "gas": 200_000,
        "gasPrice": w3.eth.gas_price,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    return {
        "tx_hash": receipt.transactionHash.hex(),
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "status": "success" if receipt.status == 1 else "failed",
    }


def verify_hash(file_hash: str) -> dict:
    """
    调用合约的 verify(fileHash) 视图方法。

    Args:
        file_hash: 0x 前缀的 SHA-256 文件哈希。

    Returns:
        包含 owner, timestamp, uri, registered 的字典。
        如果 timestamp 为 0，表示该哈希尚未注册。
    """
    w3, contract = _get_contract()
    hash_bytes = bytes.fromhex(file_hash.replace("0x", ""))

    owner, timestamp, uri = contract.functions.verify(hash_bytes).call()

    return {
        "owner": owner,
        "timestamp": timestamp,
        "uri": uri,
        "registered": timestamp != 0,
    }
