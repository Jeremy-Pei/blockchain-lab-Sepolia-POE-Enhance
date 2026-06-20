"""
query_evidence.py — Query evidence records

Provides both CLI and programmatic access to evidence records stored
in the local database.
"""

import sys

from proof_client import evidence_repository as repo


def query_by_hash(file_hash: str) -> None:
    """Find and print an evidence record by file hash."""
    record = repo.find_by_hash(file_hash)
    if record is None:
        print(f"❌ No evidence record found for hash {file_hash}.")
        return

    _print_record(record)


def query_by_owner(owner: str) -> None:
    """Find and print evidence records by owner address."""
    records = repo.find_by_owner(owner)
    if not records:
        print(f"❌ No evidence records found for owner {owner}.")
        return

    print(f"📋 Found {len(records)} record(s):")
    print()
    for r in records:
        _print_record(r)
        print()


def query_all() -> None:
    """Print all evidence records."""
    records = repo.find_all()
    total = repo.count()

    if not records:
        print("⚠️  No evidence records in the database.")
        return

    print(f"📋 Total {total} evidence record(s):")
    print()
    for r in records:
        _print_record(r)
        print()


def query_stats() -> None:
    """Print evidence statistics."""
    total = repo.count()
    records = repo.find_all()

    print(f"📊 Evidence Statistics")
    print(f"   Total records:    {total}")

    if records:
        owners = set(r.owner for r in records)
        print(f"   Unique addresses: {len(owners)}")

        success = sum(1 for r in records if r.status == "success")
        print(f"   Succeeded:        {success}")
        print(f"   Failed:           {total - success}")


def _print_record(record) -> None:
    """Format and print a single evidence record."""
    print(f"  📄 File name:  {record.file_name}")
    print(f"  🔑 Hash:       {record.file_hash}")
    print(f"  🔗 Tx Hash:    0x{record.tx_hash}")
    print(f"  📦 Block:      {record.block_number}")
    print(f"  👤 Owner:      {record.owner}")
    print(f"  ⏰ Timestamp:  {record.timestamp_utc}")
    print(f"  📌 Status:     {record.status}")


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m proof_client.query_evidence --all              # all records")
        print("  python -m proof_client.query_evidence --hash <file_hash> # by hash")
        print("  python -m proof_client.query_evidence --owner <address>  # by address")
        print("  python -m proof_client.query_evidence --stats            # statistics")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "--all":
        query_all()
    elif cmd == "--hash" and len(sys.argv) > 2:
        query_by_hash(sys.argv[2])
    elif cmd == "--owner" and len(sys.argv) > 2:
        query_by_owner(sys.argv[2])
    elif cmd == "--stats":
        query_stats()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
