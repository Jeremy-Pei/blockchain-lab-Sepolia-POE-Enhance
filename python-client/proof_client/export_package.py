"""
export_package.py — CLI for exporting evidence packages

Usage:
  python -m proof_client.export_package --hash <file_hash>
  python -m proof_client.export_package --id   <row_id>
  python -m proof_client.export_package --all
"""

import sys
from pathlib import Path

from proof_client.config import PROJECT_ROOT
from proof_client import evidence_repository as repo
from proof_client.package_exporter import export_by_hash, export_all, export_package

PACKAGES_DIR = PROJECT_ROOT / "packages"


def _usage():
    print("Usage:")
    print("  python -m proof_client.export_package --hash <file_hash>")
    print("  python -m proof_client.export_package --id   <row_id>")
    print("  python -m proof_client.export_package --all")
    sys.exit(1)


def main():
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) < 2:
        _usage()

    flag = sys.argv[1]

    if flag == "--all":
        export_all(PACKAGES_DIR)

    elif flag == "--hash" and len(sys.argv) >= 3:
        file_hash = sys.argv[2]
        result = export_by_hash(file_hash, PACKAGES_DIR)
        if result is None:
            sys.exit(1)

    elif flag == "--id" and len(sys.argv) >= 3:
        try:
            row_id = int(sys.argv[2])
        except ValueError:
            print(f"❌ Invalid id: {sys.argv[2]}")
            sys.exit(1)

        record = repo.find_by_id(row_id)
        if record is None:
            print(f"❌ No evidence record with id={row_id}")
            sys.exit(1)
        export_package(record, PACKAGES_DIR)

    else:
        _usage()


if __name__ == "__main__":
    main()
