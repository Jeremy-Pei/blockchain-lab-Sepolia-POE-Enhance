"""
batch_register.py — Batch file registration

Scans the works/ directory and registers every file on-chain.
"""

import sys
from pathlib import Path

from proof_client.config import WORKS_DIR
from proof_client.register_file import register_file
from proof_client.evidence_schema import EvidenceRecord


def batch_register(
    directory: str | Path | None = None,
    pattern: str = "*",
) -> list[EvidenceRecord]:
    """
    Register all files in a directory on-chain.

    Args:
        directory: Directory to scan; defaults to works/.
        pattern: Glob pattern; defaults to '*' (all files).

    Returns:
        List of successfully registered EvidenceRecord instances.
    """
    dir_path = Path(directory) if directory else WORKS_DIR

    if not dir_path.exists():
        print(f"❌ Directory not found: {dir_path}")
        return []

    # Collect files (exclude hidden files and directories)
    files = sorted(
        f for f in dir_path.glob(pattern)
        if f.is_file() and not f.name.startswith(".")
    )

    if not files:
        print(f"⚠️  No matching files found in {dir_path}.")
        return []

    print(f"📂 Found {len(files)} file(s) to register:")
    for i, f in enumerate(files, 1):
        print(f"   {i}. {f.name}")
    print()

    results: list[EvidenceRecord] = []
    failed: list[tuple[str, str]] = []

    for i, f in enumerate(files, 1):
        print(f"{'='*60}")
        print(f"[{i}/{len(files)}] Registering: {f.name}")
        print(f"{'='*60}")
        try:
            record = register_file(str(f))
            results.append(record)
        except Exception as e:
            print(f"❌ Registration failed: {e}")
            failed.append((f.name, str(e)))
        print()

    # Summary
    print(f"{'='*60}")
    print(f"📊 Batch registration complete")
    print(f"   Succeeded: {len(results)}")
    print(f"   Failed:    {len(failed)}")
    if failed:
        print(f"   Failed files:")
        for name, err in failed:
            print(f"     - {name}: {err}")

    return results


# ── CLI entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else None
    batch_register(directory)
