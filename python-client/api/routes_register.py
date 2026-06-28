"""
routes_register.py — Single-file on-chain registration endpoints.

Three variants:
  POST /register/file                 plain registration (uri = sepolia://<name>)
  POST /register/file/ipfs            upload plaintext to IPFS, register ipfs://<cid>
  POST /register/file/encrypted-ipfs  encrypt locally, upload ciphertext, register

Security: the encryption ``password`` is accepted as a form field but is never
written to logs and never returned in the response.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from api import services

router = APIRouter()


def _save_or_400(file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    try:
        return services.save_upload(file.file, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/file")
def register_file_api(
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    description: str = Form(""),
):
    """Register a file's hash on-chain (no off-chain upload)."""
    saved_path = _save_or_400(file)
    return services.register_file_workflow(
        file_path=saved_path,
        title=title,
        author=author,
        description=description,
        upload_ipfs=False,
        encrypt_before_ipfs=False,
    )


@router.post("/file/ipfs")
def register_file_ipfs_api(
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    description: str = Form(""),
    ipfs_provider: str = Form("mock"),
):
    """Upload the plaintext file to IPFS, then register ipfs://<cid> on-chain."""
    saved_path = _save_or_400(file)
    return services.register_file_workflow(
        file_path=saved_path,
        title=title,
        author=author,
        description=description,
        upload_ipfs=True,
        ipfs_provider=ipfs_provider,
        encrypt_before_ipfs=False,
    )


@router.post("/file/encrypted-ipfs")
def register_file_encrypted_ipfs_api(
    file: UploadFile = File(...),
    password: str = Form(...),
    title: str = Form(""),
    author: str = Form(""),
    description: str = Form(""),
    ipfs_provider: str = Form("mock"),
):
    """Encrypt the file locally, upload only the ciphertext to IPFS, register."""
    if not password:
        raise HTTPException(status_code=400, detail="Password must not be empty")
    saved_path = _save_or_400(file)
    result = services.register_file_workflow(
        file_path=saved_path,
        title=title,
        author=author,
        description=description,
        upload_ipfs=True,
        ipfs_provider=ipfs_provider,
        encrypt_before_ipfs=True,
        password=password,
    )
    # Belt-and-suspenders: never return the password.
    result.pop("password", None)
    return result
