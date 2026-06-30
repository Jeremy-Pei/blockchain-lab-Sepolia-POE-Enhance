"""
routes_verify.py — File and Merkle-proof verification endpoints.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from api import services

router = APIRouter()


@router.post("/file")
def verify_file_api(
    file: UploadFile = File(...),
    network: str = Form(""),
):
    """Verify whether an uploaded file's hash is registered on-chain."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    try:
        saved_path = services.save_upload(file.file, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return services.verify_file_workflow(saved_path, network_key=network or None)


@router.post("/merkle-proof")
def verify_merkle_proof_api(
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
