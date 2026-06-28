"""
routes_packages.py — Evidence package export, listing, and download.

Download is restricted to files inside PACKAGES_DIR; any package name that
contains path separators or ".." is rejected before touching the filesystem.
"""

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import FileResponse

from proof_client import config

from api import services

router = APIRouter()


@router.post("/export")
def export_package_api(file_hash: str = Form(...)):
    """Export a self-contained evidence package (directory + ZIP) for a hash."""
    try:
        return services.export_package_workflow(file_hash)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("")
def list_packages_api():
    """List ZIP evidence packages available for download."""
    return services.list_packages()


@router.get("/{package_name}")
def download_package(package_name: str):
    """Download a single evidence package ZIP by name."""
    if ".." in package_name or "/" in package_name or "\\" in package_name:
        raise HTTPException(status_code=400, detail="Invalid package name")

    package_path = config.PACKAGES_DIR / package_name
    # Resolve and confirm the path stays within PACKAGES_DIR.
    try:
        resolved = package_path.resolve()
        resolved.relative_to(config.PACKAGES_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid package name")

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Package not found")

    return FileResponse(
        path=str(resolved),
        filename=package_name,
        media_type="application/zip",
    )
