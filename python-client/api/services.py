"""
services.py — Adapter layer between FastAPI routes and proof_client.

The route handlers stay thin: they parse the HTTP request, call one of the
``*_workflow`` functions here, and return the resulting dict. All blockchain /
IPFS / filesystem work is delegated to the already-tested proof_client modules.

Design notes:
  - Every workflow returns a plain ``dict`` (JSON-serialisable), never a
    dataclass, so routes can return it directly.
  - Encryption passwords are accepted as arguments but are NEVER echoed back
    into any returned dict.
  - Directory constants are read from the ``config`` module at call time
    (``config.UPLOADS_DIR`` rather than a bare import) so tests can redirect
    them to a temporary location via monkeypatching.
"""

import json
import shutil
from pathlib import Path
from typing import Any, BinaryIO, Optional

from proof_client import config
from proof_client import evidence_repository as repo
from proof_client.hash_file import sha256_hash


# ── Upload handling ────────────────────────────────────────────────


def _safe_name(filename: str) -> str:
    """Reduce an uploaded filename to a basename (defuse path traversal)."""
    name = Path(filename).name
    if not name or name in {".", ".."}:
        raise ValueError("Invalid filename")
    return name


def save_upload(fileobj: BinaryIO, filename: str, dest_dir: Optional[Path] = None) -> Path:
    """Persist an uploaded file stream to ``dest_dir`` (defaults to UPLOADS_DIR).

    Returns the path the file was written to.
    """
    target_dir = dest_dir or config.UPLOADS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / _safe_name(filename)
    with out_path.open("wb") as f:
        shutil.copyfileobj(fileobj, f)
    return out_path


# ── File hashing ───────────────────────────────────────────────────


def hash_workflow(saved_path: Path) -> dict:
    """Compute the SHA-256 of an already-saved upload."""
    file_hash = sha256_hash(saved_path)
    return {
        "status": "ok",
        "file_name": saved_path.name,
        "file_size_bytes": saved_path.stat().st_size,
        "file_hash_algorithm": "SHA-256",
        "file_hash": file_hash,
        "saved_path": str(saved_path),
    }


# ── Registration ───────────────────────────────────────────────────


def _compose_note(title: str, author: str, description: str) -> Optional[str]:
    """Combine optional metadata fields into a single evidence note."""
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if author:
        parts.append(f"Author: {author}")
    if description:
        parts.append(f"Description: {description}")
    return " | ".join(parts) if parts else None


def _record_to_register_response(record) -> dict:
    """Map an EvidenceRecord to a register-endpoint response dict.

    Never includes any secret material — only public on-chain / IPFS data.
    """
    return {
        "status": "ok",
        "file_name": record.file_name,
        "file_hash": record.file_hash,
        "uri": record.uri,
        "transaction_hash": record.tx_hash,
        "block_number": record.block_number,
        "gas_used": record.gas_used,
        "owner": record.owner,
        "network": record.network,
        "explorer_url": record.explorer_link,
        "evidence_path": str(config.EVIDENCE_DIR / f"evidence_{record.file_hash.replace('0x', '')[:8]}.json"),
        "is_encrypted": record.is_encrypted,
        "ipfs_cid": record.ipfs_cid or None,
        "ipfs_uri": record.ipfs_uri or None,
        "record": record.to_dict(),
    }


def register_file_workflow(
    file_path: Path,
    title: str = "",
    author: str = "",
    description: str = "",
    upload_ipfs: bool = False,
    ipfs_provider: Optional[str] = None,
    encrypt_before_ipfs: bool = False,
    password: Optional[str] = None,
) -> dict:
    """Register a single file on-chain and return a public response dict.

    Wraps ``proof_client.register_file.register_file``. The ``password`` (when
    encrypting before IPFS) is passed through to the encryptor and is never
    returned in the response.
    """
    # Imported lazily so tests can monkeypatch the network seam on the module.
    from proof_client.register_file import register_file

    note = _compose_note(title, author, description)
    record = register_file(
        str(file_path),
        upload_ipfs=upload_ipfs,
        ipfs_provider=ipfs_provider,
        encrypt_before_ipfs=encrypt_before_ipfs,
        password=password,
        note=note,
    )
    response = _record_to_register_response(record)
    # Defensive: ensure no secret ever leaks back to the caller.
    response.pop("password", None)
    return response


# ── Verification ───────────────────────────────────────────────────


def verify_file_workflow(file_path: Path) -> dict:
    """Verify a file against the chain + local evidence; return a dict."""
    from proof_client.verify_file import verify_file

    result = verify_file(str(file_path))
    registered = bool(result.get("registered"))
    local = result.get("local_evidence")
    local_dict = local.to_dict() if local is not None else None
    tx_hash = local.tx_hash if local is not None else None

    if registered:
        message = "File hash is registered on-chain."
    else:
        message = "File hash is NOT registered on-chain."

    return {
        "status": "ok",
        "passed": registered,
        "message": message,
        "file_hash": result.get("file_hash"),
        "transaction_hash": tx_hash,
        "details": {
            "chain_data": result.get("chain_data"),
            "local_evidence": local_dict,
        },
    }


def verify_merkle_proof_workflow(
    file_path: Path,
    proof_path: Path,
    chain: bool = False,
) -> dict:
    """Verify a file against a Merkle proof JSON (optionally on-chain)."""
    from proof_client.verify_merkle_proof import (
        verify_file_against_proof,
        verify_on_chain,
    )

    try:
        proof_json = json.loads(proof_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "status": "ok",
            "passed": False,
            "message": f"Could not read proof file: {exc}",
            "details": {},
        }

    ok, details = verify_file_against_proof(file_path, proof_json)

    chain_ok = None
    chain_info: dict[str, Any] = {}
    if chain:
        merkle_root = proof_json.get("merkle_root", "")
        chain_ok, chain_info = verify_on_chain(merkle_root)
        details["chain_verification"] = "PASSED" if chain_ok else "FAILED"
        details["chain_info"] = chain_info

    passed = ok and (chain_ok is not False)
    message = "Verification passed." if passed else "Verification failed."

    return {
        "status": "ok",
        "passed": passed,
        "message": message,
        "file_hash": details.get("computed_file_hash"),
        "transaction_hash": proof_json.get("transaction_hash") or None,
        "details": details,
    }


# ── Packages ───────────────────────────────────────────────────────


def export_package_workflow(
    file_hash: str,
    include_original: Optional[bool] = None,
) -> dict:
    """Export an evidence package for ``file_hash`` and return path metadata.

    Raises ValueError if no evidence exists for the hash.
    """
    from proof_client.package_exporter import export_by_hash

    result = export_by_hash(
        file_hash, config.PACKAGES_DIR, include_original=include_original
    )
    if result is None:
        raise ValueError(f"No evidence found for hash {file_hash}")

    pkg_dir, zip_path = result
    return {
        "status": "ok",
        "file_hash": file_hash,
        "package_name": pkg_dir.name,
        "package_path": str(pkg_dir),
        "zip_name": zip_path.name,
        "zip_path": str(zip_path),
    }


def list_packages() -> dict:
    """List ZIP packages currently present in PACKAGES_DIR (non-recursive)."""
    packages = []
    pkg_dir = config.PACKAGES_DIR
    if pkg_dir.is_dir():
        for p in sorted(pkg_dir.glob("*.zip")):
            packages.append(
                {
                    "package_name": p.name,
                    "size_bytes": p.stat().st_size,
                }
            )
    return {"status": "ok", "count": len(packages), "packages": packages}


# ── Batches ────────────────────────────────────────────────────────


def batch_merkle_register_workflow(
    folder_path: Path,
    title: str = "",
    author: str = "",
    description: str = "",
    recursive: bool = False,
    dry_run: bool = False,
) -> dict:
    """Run a batch Merkle registration over a local folder."""
    from proof_client.batch_merkle_register import run_batch_registration

    result = run_batch_registration(
        folder=folder_path,
        title=title,
        author=author,
        description=description,
        recursive=recursive,
        dry_run=dry_run,
    )
    # Normalise any Path values to strings for JSON serialisation.
    normalised = {
        k: (str(v) if isinstance(v, Path) else v) for k, v in result.items()
    }
    normalised["status"] = "ok"
    normalised["dry_run"] = dry_run
    return normalised


# ── Evidence query ─────────────────────────────────────────────────


def list_evidence_files(limit: int = 20) -> dict:
    """Return the most recent single-file evidence records."""
    records = repo.find_all()[:limit]
    return {
        "status": "ok",
        "count": len(records),
        "records": [r.to_dict() for r in records],
    }


def get_evidence_by_hash(file_hash: str) -> Optional[dict]:
    """Return a single evidence record by file hash, or None."""
    record = repo.find_by_hash(file_hash)
    return record.to_dict() if record is not None else None


def get_evidence_by_tx(transaction_hash: str) -> Optional[dict]:
    """Return a single evidence record by transaction hash, or None."""
    target = transaction_hash.lower().removeprefix("0x")
    for record in repo.find_all():
        if record.tx_hash.lower().removeprefix("0x") == target:
            return record.to_dict()
    return None


def list_batch_records(limit: int = 20) -> dict:
    """Return the most recent batch Merkle evidence records."""
    records = repo.list_batches(limit=limit)
    return {"status": "ok", "count": len(records), "records": records}


def get_batch_record(batch_id: str) -> Optional[dict]:
    """Return a single batch evidence record by batch_id, or None."""
    return repo.find_batch_by_id(batch_id)
