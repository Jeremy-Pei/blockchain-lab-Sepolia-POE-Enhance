"""
contract_client.py — ProofOfExistence contract interaction client

Wraps the register / verify contract methods, handling transaction
building, signing, submission, and receipt waiting.
"""

from web3 import Web3
from web3.contract import Contract

from proof_client.config import CONTRACT_ADDRESS, load_abi
from proof_client.wallet import get_w3, get_account, get_chain_id


def _get_contract() -> tuple[Web3, Contract]:
    """Return a (w3, contract) tuple."""
    w3 = get_w3()
    abi = load_abi()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(CONTRACT_ADDRESS),
        abi=abi,
    )
    return w3, contract


def register_hash(file_hash: str, uri: str) -> dict:
    """
    Call the contract's register(fileHash, uri) method.

    Args:
        file_hash: 0x-prefixed SHA-256 hash of the file.
        uri: File identifier / path.

    Returns:
        Dict containing tx_hash, block_number, gas_used, and status.
    """
    w3, contract = _get_contract()
    account = get_account()

    # Convert hex string to bytes32
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
    Call the contract's verify(fileHash) view method.

    Args:
        file_hash: 0x-prefixed SHA-256 hash of the file.

    Returns:
        Dict containing owner, timestamp, uri, and registered flag.
        If timestamp is 0, the hash has not been registered.
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
