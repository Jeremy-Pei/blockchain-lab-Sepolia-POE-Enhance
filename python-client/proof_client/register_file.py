"""
register_file.py — Register a file on-chain

Full flow: compute hash → (optional) upload to IPFS → call contract register
→ persist evidence (JSON + SQLite).

When --upload-ipfs is given, the file is first pushed to IPFS and the
resulting ipfs://<cid> becomes the on-chain `uri`, while the CID and related
metadata are stored on the evidence record. The contract itself is unchanged:
the `uri` field was always intended for an off-chain resource pointer.
"""

import argparse
import sys
from getpass import getpass
from pathlib import Path

from proof_client.config import CONTRACT_ADDRESS, EXPLORER_TX_URL, IPFS_PROVIDER
from proof_client.hash_file import sha256_hash
from proof_client.wallet import get_address
from proof_client.contract_client import register_hash
from proof_client.evidence_schema import EvidenceRecord
from proof_client.evidence_store import save_evidence
from proof_client.encrypted_ipfs import encrypt_and_upload_to_ipfs
from proof_client.encrypt_file import write_metadata as _write_enc_metadata
from proof_client.crypto_utils import EncryptionResult
from proof_client.ipfs_client import get_client
from proof_client import evidence_repository as repo
from proof_client.network_config import (
    get_default_network_key,
    load_network_config,
    normalize_network_key,
)


def register_file(
    file_path: str,
    uri: str | None = None,
    upload_ipfs: bool = False,
    ipfs_provider: str | None = None,
    encrypt_before_ipfs: bool = False,
    password: str | None = None,
    note: str | None = None,
    network_key: str | None = None,
) -> EvidenceRecord:
    """
    Register a single file on the blockchain.

    Args:
        file_path: Path to the file.
        uri: Optional file identifier. Defaults to sepolia://<filename>, or
            is overridden by ipfs://<cid> when upload_ipfs is True and no
            explicit uri was supplied.
        upload_ipfs: If True, upload the file to IPFS before registering.
        ipfs_provider: Override the IPFS provider (mock / pinata).
        encrypt_before_ipfs: If True, encrypt the file locally and upload only
            the ciphertext to IPFS. Requires upload_ipfs=True. The ORIGINAL
            file hash is still what gets registered on-chain.
        password: Encryption password (only used with encrypt_before_ipfs).
            If None, the caller is prompted interactively.
        note: Optional free-text note stored on the evidence record (used by
            the Stage 10 API to carry title / author / description metadata).

    Returns:
        EvidenceRecord instance.
    """
    if encrypt_before_ipfs and not upload_ipfs:
        raise ValueError(
            "--encrypt-before-ipfs requires --upload-ipfs (only the encrypted "
            "copy is uploaded; nothing is encrypted without an upload)."
        )

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    file_name = path.name
    explicit_uri = uri is not None

    # 1) Compute hash of the ORIGINAL plaintext — the primary evidence hash.
    file_hash = sha256_hash(path)
    print(f"📄 File:    {file_name}")
    print(f"🔑 SHA-256: {file_hash}")

    # 2) Optional: upload to IPFS first so the on-chain uri can point to it
    ipfs_result = None
    enc_info: dict | None = None
    if upload_ipfs and encrypt_before_ipfs:
        if password is None:
            password = getpass("Enter encryption password: ")
            confirm = getpass("Confirm encryption password: ")
            if password != confirm:
                raise ValueError("Passwords do not match.")
        if not password:
            raise ValueError("Password must not be empty.")
        print("⏳ Encrypting and uploading ciphertext to IPFS...")
        enc_info = encrypt_and_upload_to_ipfs(path, password, ipfs_provider)
        # Persist the encryption metadata sidecar next to the ciphertext.
        _write_enc_metadata(
            EncryptionResult(
                original_path=str(path),
                encrypted_path=enc_info["encrypted_file_path"],
                original_sha256=enc_info["original_sha256"],
                encrypted_sha256=enc_info["encrypted_sha256"],
                algorithm=enc_info["algorithm"],
                kdf=enc_info["kdf"],
                kdf_iterations=enc_info["kdf_iterations"],
                salt_hex=enc_info["salt_hex"],
                nonce_hex=enc_info["nonce_hex"],
                encrypted_at_utc=enc_info["encrypted_at_utc"],
            ),
            Path(enc_info["encrypted_file_path"]),
        )
        print(f"🔒 Encrypted CID: {enc_info['encrypted_ipfs_cid']}")
        print(f"🔗 IPFS URI:      {enc_info['encrypted_ipfs_uri']}")
        if not explicit_uri:
            uri = enc_info["encrypted_ipfs_uri"]
    elif upload_ipfs:
        print("⏳ Uploading to IPFS...")
        ipfs_result = get_client(ipfs_provider).upload_file(path)
        print(f"🌀 CID:     {ipfs_result.cid}")
        print(f"🔗 IPFS URI: {ipfs_result.uri}")
        # Only override the uri if the caller did not pin it explicitly.
        if not explicit_uri:
            uri = ipfs_result.uri

    # Resolve network config (Stage 12)
    resolved_key = normalize_network_key(network_key) if network_key else get_default_network_key()
    try:
        net_cfg = load_network_config(resolved_key)
    except ValueError:
        net_cfg = None

    if uri is None:
        uri = f"{resolved_key}://{file_name}"

    # 3) Call contract
    net_label = net_cfg.display_name if net_cfg else resolved_key
    print(f"⏳ Submitting to {net_label}...")
    result = register_hash(file_hash, uri, network_key=network_key)
    print("✅ Transaction successful!")
    print(f"   Tx Hash: 0x{result['tx_hash']}")
    print(f"   Block:   {result['block_number']}")
    print(f"   Gas:     {result['gas_used']}")

    # Resolve network-specific values for the evidence record
    used_contract = result.get("contract_address") or CONTRACT_ADDRESS
    if net_cfg:
        used_network = net_cfg.display_name
        used_chain_id = net_cfg.chain_id
        # Store the base path (without the tx hash) so EvidenceRecord.explorer_link
        # can append the tx hash in the same way the legacy EXPLORER_TX_URL did.
        if net_cfg.explorer_tx_url_template:
            used_explorer_tx_url = net_cfg.explorer_tx_url_template.replace("{tx_hash}", "")
        else:
            used_explorer_tx_url = ""
        used_explorer_base = net_cfg.explorer_base_url
        used_network_key = net_cfg.network_key
    else:
        used_network = "Ethereum Sepolia"
        used_chain_id = 11155111
        used_explorer_tx_url = EXPLORER_TX_URL
        used_explorer_base = ""
        used_network_key = resolved_key

    # Stage 13: what the registration actually cost.
    from proof_client.gas_cost import calculate_gas_cost

    used_token_symbol = net_cfg.native_token_symbol if net_cfg else "ETH"
    cost = calculate_gas_cost(
        gas_used=result["gas_used"],
        effective_gas_price_wei=result.get("effective_gas_price_wei", 0),
        file_count=1,
        native_token_symbol=used_token_symbol,
    )

    # 4) Build evidence record
    record = EvidenceRecord(
        file_name=file_name,
        file_hash=file_hash,
        uri=uri,
        tx_hash=result["tx_hash"],
        block_number=result["block_number"],
        gas_used=result["gas_used"],
        owner=get_address(),
        status=result["status"],
        network=used_network,
        chain_id=used_chain_id,
        contract_address=used_contract,
        explorer_tx_url=used_explorer_tx_url,
        network_key=used_network_key,
        explorer_base_url=used_explorer_base,
        effective_gas_price_wei=cost.effective_gas_price_wei,
        total_fee_wei=cost.total_fee_wei,
        total_fee_eth=cost.total_fee_eth,
        native_token_symbol=cost.native_token_symbol,
        note=note,
    )

    # 4b) Attach IPFS metadata if a plaintext file was uploaded
    if ipfs_result is not None:
        record.ipfs_cid = ipfs_result.cid
        record.ipfs_uri = ipfs_result.uri
        record.ipfs_gateway_url = ipfs_result.gateway_url
        record.ipfs_provider = ipfs_result.provider
        record.ipfs_uploaded_at = ipfs_result.uploaded_at_utc
        record.ipfs_sha256 = ipfs_result.file_sha256

    # 4c) Attach encryption + encrypted-IPFS metadata if encrypted
    if enc_info is not None:
        record.is_encrypted = True
        record.encryption_algorithm = enc_info["algorithm"]
        record.encryption_kdf = enc_info["kdf"]
        record.encryption_kdf_iterations = enc_info["kdf_iterations"]
        record.encryption_salt_hex = enc_info["salt_hex"]
        record.encryption_nonce_hex = enc_info["nonce_hex"]
        record.encrypted_file_hash = enc_info["encrypted_sha256"]
        record.encrypted_file_name = enc_info["encrypted_file_name"]
        record.encrypted_ipfs_cid = enc_info["encrypted_ipfs_cid"]
        record.encrypted_ipfs_uri = enc_info["encrypted_ipfs_uri"]
        record.encrypted_ipfs_gateway_url = enc_info["encrypted_ipfs_gateway_url"]
        record.encrypted_ipfs_provider = enc_info["encrypted_ipfs_provider"]
        record.encrypted_ipfs_uploaded_at = enc_info["encrypted_ipfs_uploaded_at"]
        # Mirror the encrypted pointers into the generic IPFS fields so the
        # existing package/certificate IPFS sections also render. The
        # ipfs_sha256 here is the CIPHERTEXT hash (what IPFS actually stores).
        record.ipfs_cid = enc_info["encrypted_ipfs_cid"]
        record.ipfs_uri = enc_info["encrypted_ipfs_uri"]
        record.ipfs_gateway_url = enc_info["encrypted_ipfs_gateway_url"]
        record.ipfs_provider = enc_info["encrypted_ipfs_provider"]
        record.ipfs_uploaded_at = enc_info["encrypted_ipfs_uploaded_at"]
        record.ipfs_sha256 = enc_info["encrypted_sha256"]

    # 5) Dual-write: JSON + SQLite
    save_evidence(record)
    repo.insert(record)

    print(f"🔗 View on explorer: {record.explorer_link}")
    return record


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments (factored out so it can be unit-tested)."""
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.register_file",
        description="Register a file's SHA-256 hash on the blockchain.",
    )
    parser.add_argument("file_path", help="Path to the file to register")
    parser.add_argument(
        "uri", nargs="?", default=None, help="Optional URI (default: sepolia://<name>)"
    )
    parser.add_argument(
        "--upload-ipfs",
        action="store_true",
        help="Upload the file to IPFS and use ipfs://<cid> as the on-chain URI",
    )
    parser.add_argument(
        "--ipfs-provider",
        default=None,
        help=f"IPFS provider when --upload-ipfs is set (default: {IPFS_PROVIDER})",
    )
    parser.add_argument(
        "--encrypt-before-ipfs",
        action="store_true",
        help="Encrypt the file locally and upload only the ciphertext to IPFS "
        "(requires --upload-ipfs). The original file hash is still registered.",
    )
    parser.add_argument(
        "--network",
        default=None,
        help="Network key to use, e.g. anvil, sepolia, base-sepolia "
        "(default: DEFAULT_NETWORK env var, or sepolia)",
    )
    return parser.parse_args(argv)


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    try:
        register_file(
            args.file_path,
            args.uri,
            upload_ipfs=args.upload_ipfs,
            ipfs_provider=args.ipfs_provider,
            encrypt_before_ipfs=args.encrypt_before_ipfs,
            network_key=args.network,
        )
    except ValueError as exc:
        print(f"❌ {exc}")
        sys.exit(2)
