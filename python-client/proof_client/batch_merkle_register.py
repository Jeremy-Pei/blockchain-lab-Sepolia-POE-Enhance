"""
batch_merkle_register.py — Batch Merkle-root proof-of-existence registration

Collects files from a directory, builds a Merkle tree, registers the root
on-chain, and generates a full evidence package.

CLI:
  python -m proof_client.batch_merkle_register <folder> [options]

Options:
  --title TEXT          Batch title (optional)
  --author TEXT         Author name (optional)
  --description TEXT    Batch description (optional)
  --recursive           Recurse into sub-directories
  --dry-run             Build tree and evidence without submitting a transaction
"""

import argparse
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from proof_client.config import (
    BATCH_EVIDENCE_DIR,
    BATCH_PACKAGES_DIR,
    BATCH_REPORTS_DIR,
    CONTRACT_ADDRESS,
    EXPLORER_TX_URL,
    WORKS_DIR,
)
from proof_client.network_config import (
    get_default_network_key,
    load_network_config,
    normalize_network_key,
)
from proof_client.merkle_evidence import (
    BatchEvidence,
    MerkleLeaf,
    build_batch_evidence_files,
    make_batch_id,
    safe_proof_filename,
)
from proof_client.merkle_report import (
    generate_batch_markdown_certificate,
    generate_batch_pdf_certificate,
)
from proof_client.merkle_tree import (
    normalize_relative_path,
    sha256_file,
    sort_key,
)
from proof_client.manifest import write_manifest


# ── Supported extensions ──────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".doc", ".docx", ".tex",
    ".png", ".jpg", ".jpeg", ".zip",
}

# Directories to always ignore when collecting files.
_IGNORED_DIRS = {
    "evidence", "reports", "packages", "encrypted", "decrypted",
    "downloads", "mock_ipfs_storage", "__pycache__", ".venv", "venv",
    ".git",
}

# Filenames to always ignore.
_IGNORED_FILES = {".DS_Store", ".gitkeep"}


# ── File collection ───────────────────────────────────────────────


def collect_files(folder: Path, recursive: bool = False) -> list[Path]:
    """
    Return supported files in *folder* in deterministic sorted order.

    Args:
        folder: Directory to scan.
        recursive: Whether to descend into sub-directories.

    Returns:
        Sorted list of absolute file paths.
    """
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")

    if recursive:
        candidates = folder.rglob("*")
    else:
        candidates = folder.iterdir()

    collected = []
    for p in candidates:
        if not p.is_file():
            continue
        if p.name in _IGNORED_FILES:
            continue
        if p.name.startswith("."):
            continue
        # Ignore files inside explicitly excluded directories.
        rel_parts = set(p.relative_to(folder).parts[:-1])
        if rel_parts & _IGNORED_DIRS:
            continue
        if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        collected.append(p)

    # Sort by normalised relative path.
    return sorted(collected, key=lambda p: sort_key(p.relative_to(folder)))


def build_leaves(folder: Path, files: list[Path]) -> tuple[list[MerkleLeaf], list[str]]:
    """
    Compute SHA-256 for each file and build MerkleLeaf objects.

    Returns:
        (leaves, leaf_hashes) — both in the same sorted order.
    """
    leaves = []
    leaf_hashes = []
    for idx, fp in enumerate(files):
        rel = normalize_relative_path(fp.relative_to(folder))
        fhash = sha256_file(fp)
        leaf = MerkleLeaf(
            index=idx,
            relative_path=rel,
            file_name=fp.name,
            file_size_bytes=fp.stat().st_size,
            file_hash=fhash,
        )
        leaves.append(leaf)
        leaf_hashes.append(fhash)
    return leaves, leaf_hashes


# ── Verification guide for batch ─────────────────────────────────


def _build_batch_verification_guide(evidence: BatchEvidence) -> str:
    tx = evidence.transaction_hash or ""
    if tx and not tx.startswith("0x"):
        tx = "0x" + tx
    return f"""# Batch Merkle Proof Verification Guide

This guide explains how an independent party can verify that a specific file
belongs to the registered batch WITHOUT relying on this software or the issuer.

---

## What is Being Verified?

- **Batch ID:** `{evidence.batch_id}`
- **Merkle root:** `{evidence.merkle_root}`
- **Network:** {evidence.network} (Chain ID {evidence.chain_id})
- **Contract:** `{evidence.contract_address}`
- **Transaction:** `{tx}`

---

## Step 1 — Recompute the File SHA-256

```bash
shasum -a 256 <your_file>
```

Compare with `file_hash` in the corresponding `.proof.json`.

---

## Step 2 — Load the Proof File

Open `proofs/<file>.proof.json`. It contains:
- `file_hash` — expected SHA-256 of the file
- `merkle_root` — the registered root
- `leaf_index` — position of this file in the sorted leaf list
- `proof` — list of sibling hashes and positions

---

## Step 3 — Recompute the Merkle Root

For each step in `proof`:
- If `position == "right"`: compute SHA-256(current_bytes || sibling_bytes)
- If `position == "left"`:  compute SHA-256(sibling_bytes || current_bytes)

The final value must match `merkle_root` in the proof file.

---

## Step 4 — Query the Blockchain

Call `verify(merkle_root)` on the deployed contract:
- Contract: `{evidence.contract_address}`
- Argument: `{evidence.merkle_root}`

The returned `timestamp != 0` confirms the root is registered.

---

## Step 5 — Use the CLI

```bash
python -m proof_client.verify_merkle_proof \\
    --file <your_file> \\
    --proof proofs/<file>.proof.json

# With on-chain verification:
python -m proof_client.verify_merkle_proof \\
    --file <your_file> \\
    --proof proofs/<file>.proof.json \\
    --chain
```

---

## What This Proves

If all checks pass:
1. The file existed with its exact content before or at block {evidence.block_number}.
2. The registration was made by address `{evidence.owner_address or 'N/A'}`.
3. The file hash was included in the registered Merkle batch.

## What This Does Not Prove

- Legal authorship or copyright ownership.
- That the registrant is the original creator of the work.
- Anything that requires notarization or legal proceedings.

---

*Generated by proof_client*
"""


def _build_batch_verification_commands(evidence: BatchEvidence) -> str:
    tx = evidence.transaction_hash or ""
    if tx and not tx.startswith("0x"):
        tx = "0x" + tx
    return f"""# Batch Verification Commands
# Batch ID: {evidence.batch_id}
# Merkle root: {evidence.merkle_root}

# 1. Verify a single file belongs to the batch
python -m proof_client.verify_merkle_proof \\
    --file original/<filename> \\
    --proof proofs/<filename>.proof.json

# 2. Verify with on-chain confirmation
python -m proof_client.verify_merkle_proof \\
    --file original/<filename> \\
    --proof proofs/<filename>.proof.json \\
    --chain

# 3. Query blockchain directly (Python)
python3 -c "
from web3 import Web3
w3 = Web3(Web3.HTTPProvider('YOUR_RPC_URL'))
root_bytes = bytes.fromhex('{evidence.merkle_root.replace('0x', '')}')
# call verify(root_bytes) on contract {evidence.contract_address}
"

# 4. View transaction on block explorer
# {evidence.explorer_url or 'N/A'}

# Contract: {evidence.contract_address}
# Transaction: {tx}
# Block: {evidence.block_number}
# Owner: {evidence.owner_address or 'N/A'}
"""


# ── Package builder ───────────────────────────────────────────────


def _batch_readme(evidence: BatchEvidence, pkg_name: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    tx = evidence.transaction_hash or ""
    if tx and not tx.startswith("0x"):
        tx = "0x" + tx
    return f"""# Batch Evidence Package

**Package name:** {pkg_name}
**Generated at:** {now}
**Purpose:** Merkle batch proof-of-existence for {evidence.file_count} files

---

## Contents

| Path | Description |
|------|-------------|
| `original/` | Copies of the original work files |
| `batch/batch_evidence.json` | Machine-readable batch evidence record |
| `batch/merkle_tree.json` | Full Merkle tree with all levels |
| `batch/leaves.json` | Per-file leaf records |
| `batch/batch_summary.json` | At-a-glance batch summary |
| `proofs/` | Per-file Merkle proof JSON files |
| `reports/batch_certificate.md` | Human-readable Markdown certificate |
| `reports/batch_certificate.pdf` | Human-readable PDF certificate |
| `verification/batch_verification_guide.md` | Step-by-step verification guide |
| `verification/verification_commands.txt` | Copy-pasteable verification commands |
| `manifest.json` | SHA-256 checksums for all files |
| `README.md` | This file |

---

## Quick Verification

```bash
# Verify a single file belongs to this batch
python -m proof_client.verify_merkle_proof \\
    --file original/<filename> \\
    --proof proofs/<filename>.proof.json \\
    --chain
```

## Network

- **Blockchain:** {evidence.network} (Chain ID {evidence.chain_id})
- **Contract:** `{evidence.contract_address}`
- **Transaction:** `{tx}`
- **Block:** {evidence.block_number}
- **Merkle root:** `{evidence.merkle_root}`

---

*Generated by proof_client*
"""


def build_batch_package(
    evidence: BatchEvidence,
    leaves: list[MerkleLeaf],
    files: list[Path],
    folder: Path,
    batch_dir: Path,
    proofs_dir: Path,
    md_cert: Path,
    pdf_cert: Path,
) -> tuple[Path, Path]:
    """
    Assemble a batch evidence package directory and ZIP it.

    Returns:
        (package_dir, zip_path)
    """
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    short = evidence.merkle_root.replace("0x", "")[:8]
    pkg_name = f"merkle_batch_package_{now_str}_{short}"
    pkg_dir = BATCH_PACKAGES_DIR / pkg_name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # original/ — copies of source files
    orig_dir = pkg_dir / "original"
    orig_dir.mkdir(exist_ok=True)
    for fp in files:
        dest = orig_dir / fp.relative_to(folder)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fp, dest)

    # batch/ — evidence JSONs
    batch_pkg_dir = pkg_dir / "batch"
    batch_pkg_dir.mkdir(exist_ok=True)
    for fname in ("batch_evidence.json", "merkle_tree.json", "leaves.json", "batch_summary.json"):
        src = batch_dir / fname
        if src.exists():
            shutil.copy2(src, batch_pkg_dir / fname)

    # proofs/ — per-file proof JSONs
    pkg_proofs_dir = pkg_dir / "proofs"
    pkg_proofs_dir.mkdir(exist_ok=True)
    for pf in proofs_dir.glob("*.proof.json"):
        shutil.copy2(pf, pkg_proofs_dir / pf.name)

    # reports/
    rep_dir = pkg_dir / "reports"
    rep_dir.mkdir(exist_ok=True)
    if md_cert.exists():
        shutil.copy2(md_cert, rep_dir / "batch_certificate.md")
    if pdf_cert.exists():
        shutil.copy2(pdf_cert, rep_dir / "batch_certificate.pdf")

    # verification/
    ver_dir = pkg_dir / "verification"
    ver_dir.mkdir(exist_ok=True)
    (ver_dir / "batch_verification_guide.md").write_text(
        _build_batch_verification_guide(evidence), encoding="utf-8"
    )
    (ver_dir / "verification_commands.txt").write_text(
        _build_batch_verification_commands(evidence), encoding="utf-8"
    )

    # manifest.json
    write_manifest(pkg_dir)

    # README.md
    (pkg_dir / "README.md").write_text(_batch_readme(evidence, pkg_name), encoding="utf-8")

    # Re-write manifest after README
    write_manifest(pkg_dir)

    # ZIP
    zip_path = BATCH_PACKAGES_DIR / f"{pkg_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(pkg_dir.rglob("*")):
            if fp.is_file():
                zf.write(fp, fp.relative_to(BATCH_PACKAGES_DIR))

    return pkg_dir, zip_path


# ── Main registration flow ────────────────────────────────────────


def run_batch_registration(
    folder: Path,
    title: str = "",
    author: str = "",
    description: str = "",
    recursive: bool = False,
    dry_run: bool = False,
    network_key: str | None = None,
) -> dict:
    """
    Full batch Merkle registration flow.

    Returns:
        Dict with batch_id, merkle_root, tx_hash, evidence paths.
    """
    # 1. Collect files.
    files = collect_files(folder, recursive=recursive)
    if not files:
        raise ValueError(f"No supported files found in {folder}")

    print(f"Files found: {len(files)}")
    for fp in files:
        print(f"  {fp.relative_to(folder)}")

    # 2. Build leaves and compute hashes.
    leaves, leaf_hashes = build_leaves(folder, files)

    # 3. Compute Merkle root.
    from proof_client.merkle_tree import get_merkle_root
    merkle_root = get_merkle_root(leaf_hashes)
    print(f"\nMerkle root: {merkle_root}")

    # 4. Generate batch ID.
    batch_id = make_batch_id()
    uri = f"batch://{batch_id}"
    print(f"Batch ID: {batch_id}")
    print(f"URI: {uri}")

    # 5. Register on-chain (unless dry-run).
    tx_result = None
    owner_address = ""
    block_number = 0
    block_timestamp = 0
    explorer_url = ""

    # Resolve network config (Stage 12)
    resolved_key = normalize_network_key(network_key) if network_key else get_default_network_key()
    try:
        net_cfg = load_network_config(resolved_key)
    except ValueError:
        net_cfg = None

    if not dry_run:
        from proof_client.contract_client import register_hash, verify_hash
        from proof_client.wallet import get_account

        print(f"\nRegistering Merkle root on-chain ({net_cfg.display_name if net_cfg else resolved_key}) …")
        tx_result = register_hash(merkle_root, uri, network_key=network_key)
        print(f"Transaction hash: {tx_result['tx_hash']}")
        print(f"Block number: {tx_result['block_number']}")

        # Fetch block timestamp using the right Web3 provider
        if net_cfg:
            from web3 import Web3
            w3_net = Web3(Web3.HTTPProvider(net_cfg.rpc_url))
        else:
            from proof_client.wallet import get_w3
            w3_net = get_w3()
        try:
            block = w3_net.eth.get_block(tx_result["block_number"])
            block_timestamp = block.timestamp
        except Exception:
            block_timestamp = 0

        account = get_account()
        owner_address = account.address

        tx_hash_clean = tx_result["tx_hash"]
        if not tx_hash_clean.startswith("0x"):
            tx_hash_clean = "0x" + tx_hash_clean
        if net_cfg and net_cfg.explorer_base_url:
            explorer_url = f"{net_cfg.explorer_base_url.rstrip('/')}/tx/{tx_hash_clean}"
        else:
            base = EXPLORER_TX_URL.rstrip("/")
            explorer_url = f"{base}/{tx_hash_clean}"
        print(f"Explorer: {explorer_url}")
    else:
        print("\n[DRY RUN] Skipping on-chain registration.")

    # 6. Build BatchEvidence.
    used_network = net_cfg.display_name if net_cfg else "Ethereum Sepolia"
    used_chain_id = net_cfg.chain_id if net_cfg else 11155111
    used_contract = (tx_result.get("contract_address") if tx_result else None) or CONTRACT_ADDRESS
    used_explorer_base = net_cfg.explorer_base_url if net_cfg else ""
    used_network_key = net_cfg.network_key if net_cfg else resolved_key

    evidence = BatchEvidence(
        batch_id=batch_id,
        batch_title=title,
        author=author,
        description=description,
        file_count=len(leaves),
        merkle_root=merkle_root,
        uri=uri,
        owner_address=owner_address,
        transaction_hash=tx_result["tx_hash"] if tx_result else "",
        block_number=tx_result["block_number"] if tx_result else 0,
        block_timestamp=block_timestamp,
        explorer_url=explorer_url,
        contract_address=used_contract,
        network=used_network,
        chain_id=used_chain_id,
        network_key=used_network_key,
        explorer_base_url=used_explorer_base,
    )

    # 7. Write evidence files.
    paths = build_batch_evidence_files(
        batch_id=batch_id,
        leaves=leaves,
        leaf_hashes=leaf_hashes,
        evidence=evidence,
        tx_result=tx_result,
    )

    # 8. Generate certificates.
    md_cert = generate_batch_markdown_certificate(evidence, leaves, BATCH_REPORTS_DIR)
    pdf_cert = generate_batch_pdf_certificate(evidence, leaves, BATCH_REPORTS_DIR)
    print(f"Markdown certificate: {md_cert}")
    print(f"PDF certificate: {pdf_cert}")

    # 9. Insert into SQLite.
    from proof_client.evidence_repository import insert_batch_evidence
    import json as _json
    ev_dict = evidence.to_dict()
    insert_batch_evidence({
        **ev_dict,
        "batch_evidence_json": _json.dumps(ev_dict),
    })

    # 10. Build package.
    pkg_dir, zip_path = build_batch_package(
        evidence=evidence,
        leaves=leaves,
        files=files,
        folder=folder,
        batch_dir=paths["batch_dir"],
        proofs_dir=paths["proofs_dir"],
        md_cert=md_cert,
        pdf_cert=pdf_cert,
    )

    print(f"\nBatch evidence: {paths['batch_evidence']}")
    print(f"Proofs directory: {paths['proofs_dir']}")
    print(f"Package: {zip_path}")

    return {
        "batch_id": batch_id,
        "merkle_root": merkle_root,
        "uri": uri,
        "file_count": len(leaves),
        "transaction_hash": tx_result["tx_hash"] if tx_result else "",
        "explorer_url": explorer_url,
        "batch_evidence": paths["batch_evidence"],
        "proofs_dir": paths["proofs_dir"],
        "package_zip": zip_path,
    }


# ── CLI ───────────────────────────────────────────────────────────

def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Batch Merkle-root proof-of-existence registration"
    )
    parser.add_argument("folder", help="Directory containing files to register")
    parser.add_argument("--title",       default="", help="Batch title")
    parser.add_argument("--author",      default="", help="Author name")
    parser.add_argument("--description", default="", help="Batch description")
    parser.add_argument("--recursive",   action="store_true",
                        help="Recurse into sub-directories")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Build tree and evidence without blockchain transaction")
    parser.add_argument("--network",     default=None,
                        help="Network key, e.g. anvil, sepolia, base-sepolia "
                        "(default: DEFAULT_NETWORK env var, or sepolia)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"Error: {folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    try:
        result = run_batch_registration(
            folder=folder,
            title=args.title,
            author=args.author,
            description=args.description,
            recursive=args.recursive,
            dry_run=args.dry_run,
            network_key=args.network,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        raise
