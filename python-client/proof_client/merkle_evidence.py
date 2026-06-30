"""
merkle_evidence.py — Data structures and JSON serialisation for batch evidence

Provides:
  MerkleLeaf     — per-file record (hash, path, proof JSON, optional IPFS/enc)
  BatchEvidence  — top-level batch record (root, tx hash, all leaves)
  write_*        — write leaves.json, merkle_tree.json, per-file proof JSONs,
                   and batch_evidence.json to the batch evidence directory.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from proof_client.config import (
    BATCH_EVIDENCE_DIR,
    CHAIN_ID,
    CONTRACT_ADDRESS,
    EXPLORER_TX_URL,
)
from proof_client.merkle_tree import build_merkle_tree, generate_proof, get_merkle_root


# ── Data classes ──────────────────────────────────────────────────


@dataclass
class MerkleLeaf:
    """Per-file record inside a Merkle batch."""

    index: int
    relative_path: str
    file_name: str
    file_size_bytes: int
    file_hash: str

    # Optional IPFS fields (Stage 7 / Stage 8 compat)
    ipfs_cid: str = ""
    ipfs_uri: str = ""
    encrypted: bool = False
    encrypted_file_hash: str = ""
    encrypted_ipfs_cid: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BatchEvidence:
    """Top-level batch proof-of-existence record."""

    record_type: str = "merkle_batch"
    evidence_version: str = "1.0"
    batch_id: str = ""
    batch_title: str = ""
    author: str = ""
    description: str = ""

    file_count: int = 0
    merkle_root: str = ""
    uri: str = ""

    leaf_hash_algorithm: str = "SHA-256"
    merkle_algorithm: str = "SHA-256(left || right)"
    leaf_ordering: str = "normalized_relative_path_ascending"
    odd_leaf_strategy: str = "duplicate_last_leaf"

    network: str = "Ethereum Sepolia"
    chain_id: int = field(default_factory=lambda: CHAIN_ID)
    contract_address: str = field(default_factory=lambda: CONTRACT_ADDRESS)
    owner_address: str = ""
    transaction_hash: str = ""
    block_number: int = 0
    block_timestamp: int = 0
    explorer_url: str = ""

    # Stage 12: multi-network fields (backward-compatible defaults)
    network_key: str = ""
    explorer_base_url: str = ""

    created_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> dict:
        return asdict(self)


# ── Batch-ID generation ───────────────────────────────────────────


def make_batch_id() -> str:
    """Generate a batch ID based on current UTC date and time."""
    return datetime.now(timezone.utc).strftime("batch_%Y%m%d_%H%M%S")


# ── Safe filename for proof files ─────────────────────────────────


def safe_proof_filename(relative_path: str) -> str:
    """
    Convert a relative path to a safe proof filename stem.
    e.g. 'sub/my file.pdf' → 'sub_my_file.pdf.proof.json'
    """
    # Normalise unicode, replace path separators and spaces with underscores.
    name = unicodedata.normalize("NFC", relative_path)
    name = name.replace("/", "_").replace("\\", "_").replace(" ", "_")
    # Remove characters that are unsafe in filenames.
    name = re.sub(r"[^\w.\-]", "_", name)
    return name + ".proof.json"


# ── Write helpers ─────────────────────────────────────────────────


def write_leaves(batch_dir: Path, leaves: list[MerkleLeaf]) -> Path:
    """Write leaves.json to batch_dir."""
    path = batch_dir / "leaves.json"
    path.write_text(
        json.dumps([lf.to_dict() for lf in leaves], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def write_merkle_tree_json(batch_dir: Path, leaf_hashes: list[str]) -> tuple[Path, str]:
    """
    Build the Merkle tree from leaf_hashes and write merkle_tree.json.

    Returns:
        (path, merkle_root)
    """
    levels = build_merkle_tree(leaf_hashes)
    merkle_root = levels[-1][0]
    data = {
        "algorithm": "SHA-256(left || right)",
        "leaf_hash_algorithm": "SHA-256(file bytes)",
        "leaf_ordering": "normalized_relative_path_ascending",
        "odd_leaf_strategy": "duplicate_last_leaf",
        "levels": levels,
        "merkle_root": merkle_root,
    }
    path = batch_dir / "merkle_tree.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path, merkle_root


def write_proof_json(
    proofs_dir: Path,
    leaf: MerkleLeaf,
    merkle_root: str,
    batch_id: str,
    leaf_hashes: list[str],
    tx_result: Optional[dict] = None,
    evidence: Optional["BatchEvidence"] = None,
) -> Path:
    """
    Generate and write the proof JSON for a single leaf.

    Args:
        proofs_dir: Directory to write the proof file into.
        leaf: MerkleLeaf data for this file.
        merkle_root: Computed Merkle root (0x-prefixed hex).
        batch_id: Batch identifier string.
        leaf_hashes: Full list of leaf hashes in sorted order.
        tx_result: Optional dict from contract_client.register_hash; if None
                   the on-chain fields are left as empty strings.
        evidence: Optional BatchEvidence; used to copy network fields into the
                  proof so verifiers know which chain to query (Stage 12).

    Returns:
        Path to the written proof JSON file.
    """
    proofs_dir.mkdir(parents=True, exist_ok=True)

    proof_steps = generate_proof(leaf_hashes, leaf.index)

    tx_hash = ""
    explorer_url = ""
    if tx_result:
        tx_hash = tx_result.get("tx_hash", "")
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
        base = EXPLORER_TX_URL.rstrip("/")
        explorer_url = f"{base}/{tx_hash}"

    # Stage 12: prefer network info from BatchEvidence when available.
    net_display = evidence.network if evidence else "Ethereum Sepolia"
    net_chain_id = evidence.chain_id if evidence else CHAIN_ID
    net_contract = evidence.contract_address if evidence else CONTRACT_ADDRESS
    net_key = evidence.network_key if evidence else ""
    net_explorer_base = evidence.explorer_base_url if evidence else ""
    if evidence and evidence.explorer_url:
        explorer_url = evidence.explorer_url
    elif tx_hash:
        # build from explorer_base_url if available
        if net_explorer_base:
            explorer_url = f"{net_explorer_base.rstrip('/')}/tx/{tx_hash}"

    proof_data = {
        "proof_type": "merkle_file_proof",
        "batch_id": batch_id,
        "file_name": leaf.file_name,
        "relative_path": leaf.relative_path,
        "file_hash": leaf.file_hash,
        "merkle_root": merkle_root,
        "leaf_index": leaf.index,
        "proof": proof_steps,
        "network": net_display,
        "network_key": net_key,
        "chain_id": net_chain_id,
        "contract_address": net_contract,
        "transaction_hash": tx_hash,
        "explorer_url": explorer_url,
    }

    filename = safe_proof_filename(leaf.relative_path)
    path = proofs_dir / filename
    path.write_text(json.dumps(proof_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_batch_evidence(
    batch_dir: Path,
    evidence: BatchEvidence,
) -> Path:
    """Write batch_evidence.json to batch_dir."""
    path = batch_dir / "batch_evidence.json"
    path.write_text(
        json.dumps(evidence.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path


def write_batch_summary(batch_dir: Path, evidence: BatchEvidence, leaves: list[MerkleLeaf]) -> Path:
    """Write batch_summary.json — compact at-a-glance summary."""
    summary = {
        "batch_id": evidence.batch_id,
        "batch_title": evidence.batch_title,
        "file_count": evidence.file_count,
        "merkle_root": evidence.merkle_root,
        "transaction_hash": evidence.transaction_hash,
        "network": evidence.network,
        "created_at_utc": evidence.created_at_utc,
        "files": [
            {"index": lf.index, "relative_path": lf.relative_path, "file_hash": lf.file_hash}
            for lf in leaves
        ],
    }
    path = batch_dir / "batch_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ── Batch directory setup ─────────────────────────────────────────


def setup_batch_dir(batch_id: str) -> tuple[Path, Path]:
    """
    Create the evidence directory tree for a batch.

    Returns:
        (batch_dir, proofs_dir)
    """
    batch_dir = BATCH_EVIDENCE_DIR / batch_id
    proofs_dir = batch_dir / "proofs"
    batch_dir.mkdir(parents=True, exist_ok=True)
    proofs_dir.mkdir(parents=True, exist_ok=True)
    return batch_dir, proofs_dir


# ── Convenience: build everything for a batch ────────────────────


def build_batch_evidence_files(
    batch_id: str,
    leaves: list[MerkleLeaf],
    leaf_hashes: list[str],
    evidence: BatchEvidence,
    tx_result: Optional[dict] = None,
) -> dict:
    """
    Write all evidence files for a batch and return a summary dict of paths.

    Args:
        batch_id: Batch identifier string.
        leaves: List of MerkleLeaf objects (in sorted order).
        leaf_hashes: Parallel list of 0x-prefixed file hashes.
        evidence: BatchEvidence instance (tx_result fields should be set already).
        tx_result: Dict from contract_client.register_hash (optional).

    Returns:
        Dict with paths: batch_dir, proofs_dir, batch_evidence, leaves_json,
                         merkle_tree_json, batch_summary, proof_files.
    """
    batch_dir, proofs_dir = setup_batch_dir(batch_id)

    # Write core files.
    mt_path, _ = write_merkle_tree_json(batch_dir, leaf_hashes)
    lv_path = write_leaves(batch_dir, leaves)
    be_path = write_batch_evidence(batch_dir, evidence)
    bs_path = write_batch_summary(batch_dir, evidence, leaves)

    # Write per-file proofs.
    proof_files = []
    for leaf in leaves:
        pf = write_proof_json(
            proofs_dir, leaf, evidence.merkle_root, batch_id, leaf_hashes,
            tx_result, evidence=evidence,
        )
        proof_files.append(pf)

    return {
        "batch_dir": batch_dir,
        "proofs_dir": proofs_dir,
        "batch_evidence": be_path,
        "leaves_json": lv_path,
        "merkle_tree_json": mt_path,
        "batch_summary": bs_path,
        "proof_files": proof_files,
    }
