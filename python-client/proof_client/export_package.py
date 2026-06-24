"""
export_package.py — CLI for exporting evidence packages

Usage:
  python -m proof_client.export_package --hash <file_hash>
  python -m proof_client.export_package --id   <row_id>
  python -m proof_client.export_package --all

Original-file policy (Stage 8):
  By default the plaintext original is EXCLUDED for encrypted records and
  INCLUDED for plain records. Override with:
  --include-original   always bundle the plaintext original
  --exclude-original   never bundle the plaintext original
"""

import argparse
import sys
from pathlib import Path

from proof_client.config import PROJECT_ROOT
from proof_client import evidence_repository as repo
from proof_client.package_exporter import export_by_hash, export_all, export_package

PACKAGES_DIR = PROJECT_ROOT / "packages"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.export_package",
        description="Export a verifiable evidence package (directory + ZIP).",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--hash", help="Export the record with this file hash")
    target.add_argument("--id", type=int, help="Export the record with this row id")
    target.add_argument("--all", action="store_true", help="Export every record")

    orig = parser.add_mutually_exclusive_group()
    orig.add_argument(
        "--include-original",
        dest="include_original",
        action="store_true",
        default=None,
        help="Always bundle the plaintext original file",
    )
    orig.add_argument(
        "--exclude-original",
        dest="include_original",
        action="store_false",
        help="Never bundle the plaintext original file",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    if args.all:
        export_all(PACKAGES_DIR, include_original=args.include_original)
    elif args.hash:
        result = export_by_hash(
            args.hash, PACKAGES_DIR, include_original=args.include_original
        )
        if result is None:
            sys.exit(1)
    elif args.id is not None:
        record = repo.find_by_id(args.id)
        if record is None:
            print(f"❌ No evidence record with id={args.id}")
            sys.exit(1)
        export_package(record, PACKAGES_DIR, include_original=args.include_original)


if __name__ == "__main__":
    main()
