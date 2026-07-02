"""
generate_gas_samples.py — Deterministic sample files for gas studies (Stage 13)

Generates fixed-content sample files so gas measurements are reproducible:
the same (index, salt) pair always produces the same bytes, hence the same
SHA-256 hash.

The ProofOfExistence contract rejects re-registration of an existing hash,
so registering the exact same content twice on one network reverts. The
*salt* parameter exists for this reason: the gas study salts samples with
its study ID by default so every study registers fresh hashes, while an
explicit --salt makes runs byte-for-byte reproducible.

CLI:
  python -m proof_client.generate_gas_samples --output-dir gas_samples --count 20
"""

import argparse
import sys
from pathlib import Path


def sample_content(index: int, salt: str = "") -> str:
    """Return the deterministic content for sample file *index*."""
    lines = [
        f"Gas study sample file {index:03d}",
        "Stage 13 deterministic test content.",
    ]
    if salt:
        lines.append(f"Salt: {salt}")
    return "\n".join(lines) + "\n"


def generate_gas_samples(
    output_dir: Path,
    count: int = 20,
    salt: str = "",
) -> list[Path]:
    """Write *count* deterministic sample files and return their paths."""
    if count < 1:
        raise ValueError("count must be >= 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(1, count + 1):
        p = output_dir / f"file_{i:03d}.txt"
        p.write_text(sample_content(i, salt), encoding="utf-8")
        paths.append(p)
    return paths


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m proof_client.generate_gas_samples",
        description="Generate deterministic sample files for gas studies.",
    )
    parser.add_argument("--output-dir", default="gas_samples",
                        help="Directory to write sample files into")
    parser.add_argument("--count", type=int, default=20,
                        help="Number of sample files (default 20)")
    parser.add_argument("--salt", default="",
                        help="Optional salt mixed into the file content")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    try:
        paths = generate_gas_samples(Path(args.output_dir), args.count, args.salt)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Generated {len(paths)} sample files in {Path(args.output_dir).resolve()}")
