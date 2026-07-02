"""
gas_study.py — Standardised gas cost study across evidence workflows (Stage 13)

Runs a set of standard experiments on a chosen network and records the gas
cost of each transaction:

  single_file      N files → N register() transactions
  merkle_batch     N files → 1 register(merkle_root) transaction
  ipfs             optional: upload to IPFS, register with ipfs:// URI
  encrypted_ipfs   optional: encrypt + upload, register with ipfs:// URI

Outputs (under reports/gas_studies/<study_id>/):
  gas_study.json      full study record
  gas_study.csv       flat per-transaction table
  transactions.json   raw per-transaction results
  gas_study.md        Markdown report   (via gas_report.py)
  gas_study_report.pdf PDF report       (via gas_report.py)
  README.md           study overview

CLI:
  python -m proof_client.gas_study --network sepolia --batch-size 5 --confirm
  python -m proof_client.gas_study --network base-sepolia --dry-run

SECURITY: broadcasting requires --confirm; mainnet is disabled by default.
"""

import argparse
import csv
import json
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

from proof_client.config import REPORTS_DIR
from proof_client.gas_cost import calculate_gas_cost
from proof_client.generate_gas_samples import generate_gas_samples
from proof_client.hash_file import sha256_hash
from proof_client.merkle_tree import get_merkle_root
from proof_client.network_config import (
    get_default_network_key,
    load_network_config,
    normalize_network_key,
)


GAS_STUDIES_DIR = REPORTS_DIR / "gas_studies"

WORKFLOWS = ("single_file", "ipfs", "encrypted_ipfs", "merkle_batch", "deployment")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_study_id() -> str:
    """Generate a study ID based on the current UTC date and time."""
    return datetime.now(timezone.utc).strftime("gas_study_%Y%m%d_%H%M%S")


# ── Data classes ──────────────────────────────────────────────────


@dataclass
class GasStudyRecord:
    """One measured transaction inside a gas study."""

    study_id: str
    workflow: str
    network_key: str
    network_display_name: str
    chain_id: int
    contract_address: str
    transaction_hash: str
    block_number: int
    gas_used: int
    effective_gas_price_wei: int
    total_fee_wei: int
    total_fee_eth: str
    native_token_symbol: str
    file_count: int
    cost_per_file_wei: int
    cost_per_file_eth: str
    merkle_root: str = ""
    file_hash: str = ""
    created_at_utc: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GasStudyRecord":
        fields = cls.__dataclass_fields__
        clean = {k: v for k, v in data.items() if k in fields}
        return cls(**clean)


# ── Record builder ────────────────────────────────────────────────


def build_study_record(
    study_id: str,
    workflow: str,
    net_cfg,
    tx_result: dict,
    file_count: int = 1,
    merkle_root: str = "",
    file_hash: str = "",
) -> GasStudyRecord:
    """Convert a register_hash() result into a GasStudyRecord."""
    cost = calculate_gas_cost(
        gas_used=tx_result.get("gas_used", 0),
        effective_gas_price_wei=tx_result.get("effective_gas_price_wei", 0),
        file_count=file_count,
        native_token_symbol=net_cfg.native_token_symbol,
    )
    tx_hash = tx_result.get("tx_hash", "")
    if tx_hash and not tx_hash.startswith("0x"):
        tx_hash = "0x" + tx_hash
    return GasStudyRecord(
        study_id=study_id,
        workflow=workflow,
        network_key=net_cfg.network_key,
        network_display_name=net_cfg.display_name,
        chain_id=net_cfg.chain_id,
        contract_address=tx_result.get("contract_address", ""),
        transaction_hash=tx_hash,
        block_number=tx_result.get("block_number", 0),
        gas_used=cost.gas_used,
        effective_gas_price_wei=cost.effective_gas_price_wei,
        total_fee_wei=cost.total_fee_wei,
        total_fee_eth=cost.total_fee_eth,
        native_token_symbol=cost.native_token_symbol,
        file_count=file_count,
        cost_per_file_wei=cost.cost_per_file_wei,
        cost_per_file_eth=cost.cost_per_file_eth,
        merkle_root=merkle_root,
        file_hash=file_hash,
    )


# ── Experiments ───────────────────────────────────────────────────


def run_single_file_experiment(
    study_id: str, net_cfg, files: list[Path], network_key: str
) -> list[GasStudyRecord]:
    """Register each file individually: N files → N transactions."""
    from proof_client.contract_client import register_hash

    records = []
    for fp in files:
        file_hash = sha256_hash(fp)
        uri = f"gas-study://{study_id}/single/{fp.name}"
        print(f"  ▸ single_file: {fp.name} …")
        result = register_hash(file_hash, uri, network_key=network_key)
        records.append(
            build_study_record(
                study_id, "single_file", net_cfg, result,
                file_count=1, file_hash=file_hash,
            )
        )
    return records


def run_merkle_batch_experiment(
    study_id: str, net_cfg, files: list[Path], network_key: str
) -> GasStudyRecord:
    """Register one Merkle root covering all files: N files → 1 transaction."""
    from proof_client.contract_client import register_hash

    leaf_hashes = [sha256_hash(fp) for fp in files]
    merkle_root = get_merkle_root(leaf_hashes)
    uri = f"gas-study://{study_id}/merkle_batch"
    print(f"  ▸ merkle_batch: {len(files)} files, root {merkle_root[:18]}… …")
    result = register_hash(merkle_root, uri, network_key=network_key)
    return build_study_record(
        study_id, "merkle_batch", net_cfg, result,
        file_count=len(files), merkle_root=merkle_root,
    )


def run_ipfs_experiment(
    study_id: str, net_cfg, files: list[Path], network_key: str,
    ipfs_provider: str | None = None,
) -> list[GasStudyRecord]:
    """Upload each file to IPFS, then register with the ipfs:// URI."""
    from proof_client.contract_client import register_hash
    from proof_client.ipfs_client import get_client

    records = []
    client = get_client(ipfs_provider)
    for fp in files:
        file_hash = sha256_hash(fp)
        ipfs_result = client.upload_file(fp)
        print(f"  ▸ ipfs: {fp.name} → {ipfs_result.cid[:24]}… …")
        result = register_hash(file_hash, ipfs_result.uri, network_key=network_key)
        records.append(
            build_study_record(
                study_id, "ipfs", net_cfg, result,
                file_count=1, file_hash=file_hash,
            )
        )
    return records


def run_encrypted_ipfs_experiment(
    study_id: str, net_cfg, files: list[Path], network_key: str,
    password: str, ipfs_provider: str | None = None,
) -> list[GasStudyRecord]:
    """Encrypt each file, upload the ciphertext, register the PLAINTEXT hash."""
    from proof_client.contract_client import register_hash
    from proof_client.encrypted_ipfs import encrypt_and_upload_to_ipfs

    records = []
    for fp in files:
        file_hash = sha256_hash(fp)
        enc_info = encrypt_and_upload_to_ipfs(fp, password, ipfs_provider)
        print(f"  ▸ encrypted_ipfs: {fp.name} → {enc_info['encrypted_ipfs_cid'][:24]}… …")
        result = register_hash(
            file_hash, enc_info["encrypted_ipfs_uri"], network_key=network_key
        )
        records.append(
            build_study_record(
                study_id, "encrypted_ipfs", net_cfg, result,
                file_count=1, file_hash=file_hash,
            )
        )
    return records


# ── Output writers ────────────────────────────────────────────────

CSV_COLUMNS = [
    "study_id", "network_key", "workflow", "file_count", "tx_count",
    "gas_used", "effective_gas_price_wei", "total_fee_eth",
    "cost_per_file_eth", "transaction_hash", "block_number", "created_at_utc",
]


def write_study_json(study_dir: Path, study: dict) -> Path:
    path = study_dir / "gas_study.json"
    path.write_text(json.dumps(study, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_study_csv(study_dir: Path, records: list[GasStudyRecord]) -> Path:
    path = study_dir / "gas_study.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in records:
            writer.writerow({
                "study_id": r.study_id,
                "network_key": r.network_key,
                "workflow": r.workflow,
                "file_count": r.file_count,
                "tx_count": 1,
                "gas_used": r.gas_used,
                "effective_gas_price_wei": r.effective_gas_price_wei,
                "total_fee_eth": r.total_fee_eth,
                "cost_per_file_eth": r.cost_per_file_eth,
                "transaction_hash": r.transaction_hash,
                "block_number": r.block_number,
                "created_at_utc": r.created_at_utc,
            })
    return path


def write_transactions_json(study_dir: Path, records: list[GasStudyRecord]) -> Path:
    path = study_dir / "transactions.json"
    path.write_text(
        json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _study_readme(study: dict) -> str:
    return f"""# Gas Study {study['study_id']}

- **Network:** {study['network_display_name']} (chain ID {study['chain_id']})
- **Contract:** `{study['contract_address']}`
- **Batch size:** {study['batch_size']}
- **Transactions:** {len(study['records'])}
- **Created:** {study['created_at_utc']}

## Files

| File | Description |
|------|-------------|
| `gas_study.json` | Full machine-readable study record |
| `gas_study.csv` | Flat per-transaction table |
| `transactions.json` | Raw per-transaction records |
| `gas_study.md` | Markdown report with cost analysis |
| `gas_study_report.pdf` | PDF report |

Generated by `python -m proof_client.gas_study`.
"""


# ── Main study flow ───────────────────────────────────────────────


def run_gas_study(
    network_key: str | None = None,
    batch_size: int = 5,
    sample_dir: Path | None = None,
    include_merkle: bool = True,
    include_ipfs: bool = False,
    include_encrypted_ipfs: bool = False,
    ipfs_provider: str | None = None,
    encryption_password: str = "gas-study-password",
    output_dir: Path | None = None,
    salt: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the full gas study and write all outputs.

    Returns:
        The study dict (also written to gas_study.json), including a
        "study_dir" key with the output directory.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    resolved_key = (
        normalize_network_key(network_key) if network_key else get_default_network_key()
    )
    net_cfg = load_network_config(resolved_key)

    study_id = make_study_id()
    # The salt keeps every study's hashes unique so the contract does not
    # reject them as already registered (see generate_gas_samples.py).
    used_salt = salt if salt is not None else study_id

    base_dir = output_dir or GAS_STUDIES_DIR
    study_dir = base_dir / study_id
    study_dir.mkdir(parents=True, exist_ok=True)

    workflows = ["single_file"]
    if include_ipfs:
        workflows.append("ipfs")
    if include_encrypted_ipfs:
        workflows.append("encrypted_ipfs")
    if include_merkle:
        workflows.append("merkle_batch")

    print(f"Gas study: {study_id}")
    print(f"Network:   {net_cfg.display_name} (chain ID {net_cfg.chain_id})")
    print(f"Batch size: {batch_size}")
    print(f"Workflows: {', '.join(workflows)}")

    if dry_run:
        print("\n[DRY RUN] No samples generated, no transactions broadcast.")
        return {
            "study_id": study_id,
            "network_key": net_cfg.network_key,
            "network_display_name": net_cfg.display_name,
            "chain_id": net_cfg.chain_id,
            "contract_address": "",
            "batch_size": batch_size,
            "workflows": workflows,
            "dry_run": True,
            "records": [],
            "study_dir": str(study_dir),
            "created_at_utc": utc_now_iso(),
        }

    # Per-workflow sample sets: each workflow gets its own salt so the same
    # index never produces the same hash twice within one study.
    def _samples(workflow: str) -> list[Path]:
        if sample_dir is not None:
            return sorted(p for p in Path(sample_dir).iterdir() if p.is_file())[:batch_size]
        return generate_gas_samples(
            study_dir / "samples" / workflow, batch_size,
            salt=f"{used_salt}:{workflow}",
        )

    records: list[GasStudyRecord] = []

    print("\nRunning single_file experiment …")
    records.extend(
        run_single_file_experiment(study_id, net_cfg, _samples("single_file"), resolved_key)
    )

    if include_ipfs:
        print("\nRunning ipfs experiment …")
        records.extend(
            run_ipfs_experiment(
                study_id, net_cfg, _samples("ipfs"), resolved_key, ipfs_provider
            )
        )

    if include_encrypted_ipfs:
        print("\nRunning encrypted_ipfs experiment …")
        records.extend(
            run_encrypted_ipfs_experiment(
                study_id, net_cfg, _samples("encrypted_ipfs"), resolved_key,
                encryption_password, ipfs_provider,
            )
        )

    if include_merkle:
        print("\nRunning merkle_batch experiment …")
        records.append(
            run_merkle_batch_experiment(
                study_id, net_cfg, _samples("merkle_batch"), resolved_key
            )
        )

    contract_address = records[0].contract_address if records else ""

    study = {
        "study_id": study_id,
        "network_key": net_cfg.network_key,
        "network_display_name": net_cfg.display_name,
        "chain_id": net_cfg.chain_id,
        "contract_address": contract_address,
        "native_token_symbol": net_cfg.native_token_symbol,
        "batch_size": batch_size,
        "workflows": workflows,
        "salt": used_salt,
        "dry_run": False,
        "created_at_utc": utc_now_iso(),
        "records": [r.to_dict() for r in records],
    }

    write_study_json(study_dir, study)
    write_study_csv(study_dir, records)
    write_transactions_json(study_dir, records)
    (study_dir / "README.md").write_text(_study_readme(study), encoding="utf-8")

    # Markdown + PDF reports
    from proof_client.gas_report import generate_reports

    md_path, pdf_path = generate_reports(study_dir)

    study["study_dir"] = str(study_dir)
    print(f"\n✅ Gas study complete: {study_dir}")
    print(f"   JSON: {study_dir / 'gas_study.json'}")
    print(f"   CSV:  {study_dir / 'gas_study.csv'}")
    print(f"   MD:   {md_path}")
    if pdf_path:
        print(f"   PDF:  {pdf_path}")
    return study


# ── CLI ───────────────────────────────────────────────────────────


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.gas_study",
        description="Run a standardised gas cost study on a configured network.",
    )
    parser.add_argument("--network", default=None,
                        help="Network key, e.g. anvil, sepolia, base-sepolia")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="Files per workflow (default 5)")
    parser.add_argument("--sample-dir", default=None,
                        help="Use existing sample files instead of generating them")
    parser.add_argument("--include-ipfs", action="store_true",
                        help="Also measure the IPFS registration workflow")
    parser.add_argument("--include-encrypted-ipfs", action="store_true",
                        help="Also measure the encrypted-IPFS workflow")
    parser.add_argument("--no-merkle", action="store_true",
                        help="Skip the Merkle batch experiment")
    parser.add_argument("--ipfs-provider", default=None,
                        help="IPFS provider for the IPFS workflows (default: env)")
    parser.add_argument("--output-dir", default=None,
                        help="Base output directory (default reports/gas_studies)")
    parser.add_argument("--salt", default=None,
                        help="Sample-content salt (default: the study ID)")
    parser.add_argument("--confirm", action="store_true",
                        help="Required to broadcast the study transactions")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the study plan without broadcasting")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    if not args.dry_run and not args.confirm:
        print(
            "Error: a gas study broadcasts multiple on-chain transactions and "
            "spends native tokens. Re-run with --confirm (or --dry-run).",
            file=sys.stderr,
        )
        return 2

    try:
        run_gas_study(
            network_key=args.network,
            batch_size=args.batch_size,
            sample_dir=Path(args.sample_dir) if args.sample_dir else None,
            include_merkle=not args.no_merkle,
            include_ipfs=args.include_ipfs,
            include_encrypted_ipfs=args.include_encrypted_ipfs,
            ipfs_provider=args.ipfs_provider,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            salt=args.salt,
            dry_run=args.dry_run,
        )
    except (ValueError, ConnectionError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
