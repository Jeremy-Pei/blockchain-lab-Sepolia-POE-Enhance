"""
routes_files.py — File upload + SHA-256 hashing.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile

from api import services
from api.schemas import HashResponse

router = APIRouter()


@router.post("/hash", response_model=HashResponse)
def hash_uploaded_file(file: UploadFile = File(...)) -> HashResponse:
    """Upload a file, save it under uploads/, and return its SHA-256 hash."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    try:
        saved_path = services.save_upload(file.file, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return HashResponse(**services.hash_workflow(saved_path))
