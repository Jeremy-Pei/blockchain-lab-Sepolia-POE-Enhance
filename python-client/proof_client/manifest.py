"""
manifest.py — SHA-256 manifest for evidence packages

Generates a manifest.json that lists every file in the evidence
package with its SHA-256 checksum, so that any modification to
the package is detectable.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute the SHA-256 hex digest of a bytes object."""
    return hashlib.sha256(data).hexdigest()


def build_manifest(package_dir: Path) -> dict:
    """
    Walk package_dir and return a manifest dict (not yet written to disk).
    manifest.json itself is excluded from the file list.
    """
    files = []
    for path in sorted(package_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            rel = path.relative_to(package_dir)
            files.append({
                "path": str(rel),
                "sha256": sha256_file(path),
            })

    return {
        "package_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "package_type": "ProofOfExistenceEvidencePackage",
        "files": files,
    }


def write_manifest(package_dir: Path) -> tuple[Path, str]:
    """
    Write manifest.json to package_dir.

    Returns:
        (path_to_manifest, sha256_of_manifest_content)
    """
    manifest = build_manifest(package_dir)
    manifest_path = package_dir / "manifest.json"
    content = json.dumps(manifest, indent=2, ensure_ascii=False)
    manifest_path.write_text(content, encoding="utf-8")
    manifest_hash = sha256_bytes(content.encode("utf-8"))
    return manifest_path, manifest_hash


def verify_manifest(package_dir: Path) -> tuple[bool, list[str]]:
    """
    Verify every file listed in manifest.json matches its stored hash.

    Args:
        package_dir: Extracted package directory containing manifest.json.

    Returns:
        (all_ok, list_of_error_strings)
    """
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.exists():
        return False, ["manifest.json not found"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    for entry in manifest.get("files", []):
        file_path = package_dir / entry["path"]
        if not file_path.exists():
            errors.append(f"Missing file: {entry['path']}")
            continue
        actual = sha256_file(file_path)
        if actual != entry["sha256"]:
            errors.append(
                f"Hash mismatch: {entry['path']} "
                f"(expected {entry['sha256'][:12]}..., got {actual[:12]}...)"
            )

    return len(errors) == 0, errors


def verify_manifest_in_zip(zip_path: Path) -> tuple[bool, list[str]]:
    """
    Verify manifest inside a ZIP archive without extracting it.

    Returns:
        (all_ok, list_of_error_strings)
    """
    import zipfile
    import io

    if not zip_path.exists():
        return False, [f"ZIP not found: {zip_path}"]

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        # Find manifest.json (may be inside a subdirectory)
        manifest_entries = [n for n in names if n.endswith("manifest.json")]
        if not manifest_entries:
            return False, ["manifest.json not found in ZIP"]

        manifest_entry = manifest_entries[0]
        prefix = manifest_entry[: -len("manifest.json")]

        manifest_data = json.loads(zf.read(manifest_entry).decode("utf-8"))
        errors: list[str] = []

        for entry in manifest_data.get("files", []):
            zip_member = prefix + entry["path"].replace("\\", "/")
            if zip_member not in names:
                errors.append(f"Missing file: {entry['path']}")
                continue
            raw = zf.read(zip_member)
            actual = sha256_bytes(raw)
            if actual != entry["sha256"]:
                errors.append(
                    f"Hash mismatch: {entry['path']} "
                    f"(expected {entry['sha256'][:12]}..., got {actual[:12]}...)"
                )

    return len(errors) == 0, errors
