"""
verify_package.py — CLI for verifying evidence package integrity

Checks every file in a ZIP package against the SHA-256 hashes recorded
in manifest.json, detecting any post-generation tampering.

Usage:
  python -m proof_client.verify_package <package.zip>
  python -m proof_client.verify_package <extracted_dir/>
"""

import sys
from pathlib import Path

from proof_client.manifest import verify_manifest, verify_manifest_in_zip


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m proof_client.verify_package <package.zip>")
        print("  python -m proof_client.verify_package <extracted_dir/>")
        sys.exit(1)

    target = Path(sys.argv[1])

    if not target.exists():
        print(f"❌ Not found: {target}")
        sys.exit(1)

    print(f"\n🔍 Verifying: {target}")

    if target.is_file() and target.suffix == ".zip":
        ok, errors = verify_manifest_in_zip(target)
    elif target.is_dir():
        ok, errors = verify_manifest(target)
    else:
        print(f"❌ Expected a .zip file or extracted directory, got: {target}")
        sys.exit(1)

    if ok:
        print("✅ All files match manifest.json — package is intact.")
    else:
        print("❌ Package integrity check FAILED:")
        for err in errors:
            print(f"   • {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
