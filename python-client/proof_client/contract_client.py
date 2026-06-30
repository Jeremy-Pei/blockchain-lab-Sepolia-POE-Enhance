"""
contract_client.py — ProofOfExistence contract interaction client

Wraps the register / verify contract methods, handling transaction
building, signing, submission, and receipt waiting.

Stage 12: register_hash / verify_hash now accept an optional network_key.
When network_key is supplied the function uses network_config + network_context
(with chain-ID validation) instead of the legacy config.py flat variables.
"""

from web3 import Web3
from web3.contract import Contract

from proof_client.config import CONTRACT_ADDRESS, load_abi
from proof_client.wallet import get_w3, get_account, get_chain_id


def _get_contract() -> tuple[Web3, Contract]:
    """Return a (w3, contract) tuple using the legacy config.py values."""
    w3 = get_w3()
    abi = load_abi()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(CONTRACT_ADDRESS),
        abi=abi,
    )
    return w3, contract


def _get_contract_for_network(network_key: str) -> tuple[Web3, Contract, str]:
    """Return (w3, contract, contract_address) for a specific network."""
    from proof_client.network_context import create_network_context

    ctx = create_network_context(network_key)
    abi = load_abi()
    contract = ctx.web3.eth.contract(
        address=Web3.to_checksum_address(ctx.contract_address),
        abi=abi,
    )
    return ctx.web3, contract, ctx.contract_address


def register_hash(
    file_hash: str,
    uri: str,
    network_key: str | None = None,
) -> dict:
    """
    Call the contract's register(fileHash, uri) method.

    Args:
        file_hash: 0x-prefixed SHA-256 hash of the file.
        uri: File identifier / path.
        network_key: Optional network to use (Stage 12). When None, falls
                     back to the legacy config.py RPC/contract values.

    Returns:
        Dict containing tx_hash, block_number, gas_used, status, and
        (Stage 12) network_key, contract_address.
    """
    account = get_account()

    if network_key is not None:
        w3, contract, used_contract_address = _get_contract_for_network(network_key)
        chain_id = w3.eth.chain_id
    else:
        w3, contract = _get_contract()
        used_contract_address = CONTRACT_ADDRESS
        chain_id = get_chain_id()

    hash_bytes = bytes.fromhex(file_hash.replace("0x", ""))

    tx = contract.functions.register(hash_bytes, uri).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": chain_id,
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
        "contract_address": used_contract_address,
        "network_key": network_key,
    }


def verify_hash(
    file_hash: str,
    network_key: str | None = None,
) -> dict:
    """
    Call the contract's verify(fileHash) view method.

    Args:
        file_hash: 0x-prefixed SHA-256 hash of the file.
        network_key: Optional network to use (Stage 12).

    Returns:
        Dict containing owner, timestamp, uri, and registered flag.
        If timestamp is 0, the hash has not been registered.
    """
    if network_key is not None:
        w3, contract, _ = _get_contract_for_network(network_key)
    else:
        w3, contract = _get_contract()

    hash_bytes = bytes.fromhex(file_hash.replace("0x", ""))
    owner, timestamp, uri = contract.functions.verify(hash_bytes).call()

    return {
        "owner": owner,
        "timestamp": timestamp,
        "uri": uri,
        "registered": timestamp != 0,
    }
