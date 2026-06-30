"""
routes_batches.py — Merkle batch registration and lookup endpoints.

The first version registers a batch from a *local* folder path (the service
is local-first). A future Web Dashboard can add ZIP-upload batching.
"""

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from api import services

router = APIRouter()


@router.post("/merkle/register")
def register_merkle_batch_api(
    folder_path: str = Form(...),
    title: str = Form(""),
    author: str = Form(""),
    description: str = Form(""),
    recursive: bool = Form(False),
    dry_run: bool = Form(False),
    network: str = Form(""),
):
    """Build a Merkle tree over a local folder and register its root on-chain."""
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail="Invalid folder path")
    try:
        return services.batch_merkle_register_workflow(
            folder_path=folder,
            title=title,
            author=author,
            description=description,
            recursive=recursive,
            dry_run=dry_run,
            network_key=network or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/merkle/verify")
def verify_merkle_batch_api(
    file: UploadFile = File(...),
    proof: UploadFile = File(...),
    chain: bool = Form(False),
    network: str = Form(""),
):
    """Verify a file belongs to a registered Merkle batch using its proof JSON."""
    if not file.filename or not proof.filename:
        raise HTTPException(status_code=400, detail="Missing file or proof filename")
    try:
        file_path = services.save_upload(file.file, file.filename)
        proof_path = services.save_upload(proof.file, proof.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return services.verify_merkle_proof_workflow(
        file_path=file_path,
        proof_path=proof_path,
        chain=chain,
        network_key=network or None,
    )


@router.get("")
def list_batches_api(limit: int = 20):
    """List the most recent batch Merkle evidence records."""
    return services.list_batch_records(limit=limit)


@router.get("/{batch_id}")
def get_batch_api(batch_id: str):
    """Return a single batch evidence record by batch_id."""
    record = services.get_batch_record(batch_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Batch evidence not found")
    return {"status": "ok", "record": record}
