"""
routes_dashboard.py — Stage 11 Jinja2/HTML dashboard routes.

Adds a browser-accessible UI on top of the Stage 10 FastAPI service.  All
business logic is delegated to api.services (which in turn calls proof_client);
this module only adapts HTTP requests to template responses.

SECURITY: This dashboard is designed for local development and demonstration
only. It does not implement authentication or rate limiting.  Do not expose it
to the public internet.
"""

from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.templating import Jinja2Templates

from api import services

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"
templates = Jinja2Templates(directory=str(_WEB_DIR / "templates"))

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────


def _render(request: Request, template: str, ctx: dict, status_code: int = 200):
    return templates.TemplateResponse(
        request=request,
        name=template,
        context=ctx,
        status_code=status_code,
    )


def _error(request: Request, message: str, title: str = "Error", status_code: int = 400):
    return _render(
        request,
        "error.html",
        {"title": title, "message": message},
        status_code=status_code,
    )


def _save(file: UploadFile, dest_dir: "Path | None" = None) -> Path:
    """Save an uploaded file and return its path; raises ValueError on bad name."""
    filename = file.filename or "upload"
    return services.save_upload(file.file, filename, dest_dir=dest_dir)


# ── Home ───────────────────────────────────────────────────────────


@router.get("/")
def dashboard_home(request: Request):
    """Landing page — links to all dashboard sections."""
    return _render(request, "index.html", {"title": "Proof-of-Existence Dashboard"})


# ── File hash ──────────────────────────────────────────────────────


@router.get("/dashboard/hash")
def hash_page(request: Request):
    return _render(request, "hash.html", {"title": "Hash a File"})


@router.post("/dashboard/hash")
async def hash_submit(request: Request, file: UploadFile = File(...)):
    try:
        saved = _save(file)
        result = services.hash_workflow(saved)
        return _render(request, "result.html", {"title": "Hash Result", "result": result})
    except Exception as exc:
        return _error(request, str(exc))


# ── Register ───────────────────────────────────────────────────────


@router.get("/dashboard/register")
def register_page(request: Request):
    return _render(request, "register.html", {"title": "Register Evidence"})


@router.post("/dashboard/register")
async def register_submit(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    description: str = Form(""),
    mode: str = Form("normal"),
    password: str = Form(""),
):
    try:
        saved = _save(file)
        if mode == "normal":
            result = services.register_file_workflow(
                saved, title=title, author=author, description=description
            )
        elif mode == "ipfs":
            result = services.register_file_workflow(
                saved,
                title=title,
                author=author,
                description=description,
                upload_ipfs=True,
                ipfs_provider="mock",
            )
        elif mode == "encrypted_ipfs":
            if not password:
                return _error(request, "Password is required for encrypted IPFS mode.")
            result = services.register_file_workflow(
                saved,
                title=title,
                author=author,
                description=description,
                upload_ipfs=True,
                encrypt_before_ipfs=True,
                password=password,
            )
        else:
            return _error(request, f"Unknown registration mode: {mode!r}")

        result.pop("password", None)
        return _render(
            request, "result.html", {"title": "Registration Result", "result": result}
        )
    except Exception as exc:
        return _error(request, str(exc), title="Registration Error")


# ── Verify file ────────────────────────────────────────────────────


@router.get("/dashboard/verify")
def verify_page(request: Request):
    return _render(request, "verify.html", {"title": "Verify File"})


@router.post("/dashboard/verify")
async def verify_submit(request: Request, file: UploadFile = File(...)):
    try:
        saved = _save(file)
        result = services.verify_file_workflow(saved)
        return _render(
            request, "result.html", {"title": "Verification Result", "result": result}
        )
    except Exception as exc:
        return _error(request, str(exc), title="Verification Error")


# ── Verify Merkle proof ────────────────────────────────────────────


@router.get("/dashboard/verify-merkle")
def verify_merkle_page(request: Request):
    return _render(request, "verify_merkle.html", {"title": "Verify Merkle Proof"})


@router.post("/dashboard/verify-merkle")
async def verify_merkle_submit(
    request: Request,
    file: UploadFile = File(...),
    proof: UploadFile = File(...),
    check_blockchain: str = Form(""),
):
    try:
        from proof_client import config as _cfg

        saved_file = _save(file)
        saved_proof = _save(proof, dest_dir=_cfg.API_TEMP_DIR)
        chain = check_blockchain.lower() in ("on", "true", "1", "yes")
        result = services.verify_merkle_proof_workflow(saved_file, saved_proof, chain=chain)
        return _render(
            request,
            "result.html",
            {"title": "Merkle Proof Verification", "result": result},
        )
    except Exception as exc:
        return _error(request, str(exc), title="Merkle Proof Error")


# ── Evidence browser ───────────────────────────────────────────────


@router.get("/dashboard/evidence")
def evidence_page(request: Request):
    try:
        data = services.list_evidence_files(limit=50)
        return _render(
            request,
            "evidence.html",
            {"title": "Evidence Browser", "records": data.get("records", [])},
        )
    except Exception as exc:
        return _error(request, str(exc), title="Evidence Error", status_code=500)


@router.get("/dashboard/evidence/{file_hash}")
def evidence_detail_page(request: Request, file_hash: str):
    record = services.get_evidence_by_hash(file_hash)
    if record is None:
        return _error(
            request,
            f"No evidence found for hash: {file_hash}",
            title="Not Found",
            status_code=404,
        )
    return _render(
        request,
        "evidence_detail.html",
        {"title": "Evidence Detail", "record": record},
    )


# ── Batch browser ──────────────────────────────────────────────────


@router.get("/dashboard/batches")
def batches_page(request: Request):
    try:
        data = services.list_batch_records(limit=50)
        return _render(
            request,
            "batches.html",
            {"title": "Batch Browser", "records": data.get("records", [])},
        )
    except Exception as exc:
        return _error(request, str(exc), title="Batch Error", status_code=500)


@router.get("/dashboard/batches/{batch_id}")
def batch_detail_page(request: Request, batch_id: str):
    record = services.get_batch_record(batch_id)
    if record is None:
        return _error(
            request,
            f"No batch found for ID: {batch_id}",
            title="Not Found",
            status_code=404,
        )
    return _render(
        request,
        "batch_detail.html",
        {"title": "Batch Detail", "record": record},
    )


# ── Packages ───────────────────────────────────────────────────────


@router.get("/dashboard/packages")
def packages_page(request: Request):
    try:
        from proof_client import config as _cfg

        packages = []
        for p in sorted(_cfg.PACKAGES_DIR.glob("*.zip")):
            stat = p.stat()
            packages.append(
                {
                    "name": p.name,
                    "size_bytes": stat.st_size,
                    "source": "single",
                }
            )
        for p in sorted(_cfg.BATCH_PACKAGES_DIR.glob("*.zip")):
            stat = p.stat()
            packages.append(
                {
                    "name": p.name,
                    "size_bytes": stat.st_size,
                    "source": "batch",
                }
            )
        return _render(
            request,
            "packages.html",
            {"title": "Evidence Packages", "packages": packages},
        )
    except Exception as exc:
        return _error(request, str(exc), title="Packages Error", status_code=500)
