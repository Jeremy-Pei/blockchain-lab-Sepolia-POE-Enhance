"""
wallet.py — Wallet and Web3 connection management

Provides Web3 instantiation, account loading, and transaction signing.
"""

from web3 import Web3
from eth_account import Account
from proof_client.config import RPC_URL, PRIVATE_KEY, CHAIN_ID


def get_w3() -> Web3:
    """
    Create and return a connected Web3 instance.

    Raises:
        ConnectionError: If the RPC node cannot be reached.
    """
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to RPC node: {RPC_URL}")
    return w3


def get_account() -> Account:
    """
    Create an eth_account.Account object from the private key.

    Returns:
        Account object suitable for signing transactions.
    """
    return Account.from_key(PRIVATE_KEY)


def get_address() -> str:
    """Return the current wallet address in checksum format."""
    return get_account().address


def get_chain_id() -> int:
    """Return the configured chain ID."""
    return CHAIN_ID
