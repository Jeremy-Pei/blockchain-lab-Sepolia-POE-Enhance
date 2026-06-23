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
from pathlib import Path

from proof_client.config import CONTRACT_ADDRESS, EXPLORER_TX_URL, IPFS_PROVIDER
from proof_client.hash_file import sha256_hash
from proof_client.wallet import get_address
from proof_client.contract_client import register_hash
from proof_client.evidence_schema import EvidenceRecord
from proof_client.evidence_store import save_evidence
from proof_client.ipfs_client import get_client
from proof_client import evidence_repository as repo


def register_file(
    file_path: str,
    uri: str | None = None,
    upload_ipfs: bool = False,
    ipfs_provider: str | None = None,
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

    Returns:
        EvidenceRecord instance.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    file_name = path.name
    explicit_uri = uri is not None

    # 1) Compute hash
    file_hash = sha256_hash(path)
    print(f"📄 File:    {file_name}")
    print(f"🔑 SHA-256: {file_hash}")

    # 2) Optional: upload to IPFS first so the on-chain uri can point to it
    ipfs_result = None
    if upload_ipfs:
        print("⏳ Uploading to IPFS...")
        ipfs_result = get_client(ipfs_provider).upload_file(path)
        print(f"🌀 CID:     {ipfs_result.cid}")
        print(f"🔗 IPFS URI: {ipfs_result.uri}")
        # Only override the uri if the caller did not pin it explicitly.
        if not explicit_uri:
            uri = ipfs_result.uri

    if uri is None:
        uri = f"sepolia://{file_name}"

    # 3) Call contract
    print("⏳ Submitting to Sepolia...")
    result = register_hash(file_hash, uri)
    print("✅ Transaction successful!")
    print(f"   Tx Hash: 0x{result['tx_hash']}")
    print(f"   Block:   {result['block_number']}")
    print(f"   Gas:     {result['gas_used']}")

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
        contract_address=CONTRACT_ADDRESS,
        explorer_tx_url=EXPLORER_TX_URL,
    )

    # 4b) Attach IPFS metadata if uploaded
    if ipfs_result is not None:
        record.ipfs_cid = ipfs_result.cid
        record.ipfs_uri = ipfs_result.uri
        record.ipfs_gateway_url = ipfs_result.gateway_url
        record.ipfs_provider = ipfs_result.provider
        record.ipfs_uploaded_at = ipfs_result.uploaded_at_utc
        record.ipfs_sha256 = ipfs_result.file_sha256

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
    return parser.parse_args(argv)


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    register_file(
        args.file_path,
        args.uri,
        upload_ipfs=args.upload_ipfs,
        ipfs_provider=args.ipfs_provider,
    )
