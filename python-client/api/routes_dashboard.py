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
from proof_client.network_config import get_default_network_config, list_network_configs

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"
templates = Jinja2Templates(directory=str(_WEB_DIR / "templates"))

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────


def _network_ctx() -> dict:
    """Return minimal network info for template rendering."""
    try:
        cfg = get_default_network_config()
        return {
            "current_network_key": cfg.network_key,
            "current_network_name": cfg.display_name,
            "current_chain_id": cfg.chain_id,
            "current_contract": cfg.contract_address,
            "available_networks": [
                {"key": c.network_key, "name": c.display_name}
                for c in list_network_configs()
            ],
        }
    except Exception:
        return {
            "current_network_key": "sepolia",
            "current_network_name": "Ethereum Sepolia",
            "current_chain_id": 11155111,
            "current_contract": "",
            "available_networks": [{"key": "sepolia", "name": "Ethereum Sepolia"}],
        }


def _render(request: Request, template: str, ctx: dict, status_code: int = 200):
    merged = {**_network_ctx(), **ctx}
    return templates.TemplateResponse(
        request=request,
        name=template,
        context=merged,
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
    network: str = Form(""),
):
    try:
        saved = _save(file)
        net_key = network or None
        if mode == "normal":
            result = services.register_file_workflow(
                saved, title=title, author=author, description=description,
                network_key=net_key,
            )
        elif mode == "ipfs":
            result = services.register_file_workflow(
                saved,
                title=title,
                author=author,
                description=description,
                upload_ipfs=True,
                ipfs_provider="mock",
                network_key=net_key,
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
                network_key=net_key,
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
async def verify_submit(
    request: Request,
    file: UploadFile = File(...),
    network: str = Form(""),
):
    try:
        saved = _save(file)
        result = services.verify_file_workflow(saved, network_key=network or None)
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
    network: str = Form(""),
):
    try:
        from proof_client import config as _cfg

        saved_file = _save(file)
        saved_proof = _save(proof, dest_dir=_cfg.API_TEMP_DIR)
        chain = check_blockchain.lower() in ("on", "true", "1", "yes")
        result = services.verify_merkle_proof_workflow(
            saved_file, saved_proof, chain=chain, network_key=network or None
        )
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


# ── Deployment (Stage 13) ──────────────────────────────────────────


@router.get("/dashboard/deploy")
def deploy_page(request: Request):
    return _render(request, "deploy.html", {"title": "Deploy Contract"})


@router.post("/dashboard/deploy")
async def deploy_submit(
    request: Request,
    network: str = Form(...),
    confirm: str = Form(""),
    dry_run: str = Form(""),
    update_env: str = Form(""),
):
    is_dry_run = dry_run in ("1", "on", "true")
    is_confirmed = confirm in ("1", "on", "true")

    if not is_dry_run and not is_confirmed:
        return _error(
            request,
            "Deployment requires the confirm checkbox because it broadcasts "
            "an on-chain transaction.",
            title="Confirmation Required",
        )

    try:
        from proof_client.deploy_contract import (
            deploy_contract,
            update_env_contract_address,
        )
        from proof_client.network_config import load_network_config

        record = deploy_contract(network_key=network, dry_run=is_dry_run)
        if record is None:
            result = {
                "dry_run": True,
                "network": network,
                "message": "Dry run passed: configuration, wallet, artifact "
                           "and gas estimate are valid. No transaction was "
                           "broadcast.",
            }
        else:
            if update_env in ("1", "on", "true"):
                cfg = load_network_config(network)
                update_env_contract_address(
                    cfg.contract_address_env_key, record.contract_address
                )
            result = record.to_dict()
        return _render(
            request, "result.html", {"title": "Deployment Result", "result": result}
        )
    except Exception as exc:
        return _error(request, str(exc), title="Deployment Error")


@router.get("/dashboard/deployments")
def deployments_page(request: Request):
    try:
        from proof_client.deployment_repository import list_deployment_records

        records = [r.to_dict() for r in list_deployment_records()]
        return _render(
            request,
            "deployments.html",
            {"title": "Deployment History", "records": records},
        )
    except Exception as exc:
        return _error(request, str(exc), title="Deployments Error", status_code=500)


# ── Gas study (Stage 13) ───────────────────────────────────────────


@router.get("/dashboard/gas-study")
def gas_study_page(request: Request):
    return _render(request, "gas_study.html", {"title": "Run Gas Study"})


@router.post("/dashboard/gas-study")
async def gas_study_submit(
    request: Request,
    network: str = Form(...),
    batch_size: int = Form(5),
    confirm: str = Form(""),
    dry_run: str = Form(""),
    include_merkle: str = Form(""),
    include_ipfs: str = Form(""),
    include_encrypted_ipfs: str = Form(""),
):
    is_dry_run = dry_run in ("1", "on", "true")
    is_confirmed = confirm in ("1", "on", "true")

    if not is_dry_run and not is_confirmed:
        return _error(
            request,
            "A gas study requires the confirm checkbox because it broadcasts "
            "on-chain transactions.",
            title="Confirmation Required",
        )

    try:
        from proof_client.gas_study import run_gas_study

        study = run_gas_study(
            network_key=network,
            batch_size=batch_size,
            include_merkle=include_merkle in ("1", "on", "true"),
            include_ipfs=include_ipfs in ("1", "on", "true"),
            include_encrypted_ipfs=include_encrypted_ipfs in ("1", "on", "true"),
            dry_run=is_dry_run,
        )
        if is_dry_run:
            return _render(
                request,
                "result.html",
                {"title": "Gas Study Dry Run", "result": study},
            )
        return gas_study_detail_page(request, study["study_id"])
    except Exception as exc:
        return _error(request, str(exc), title="Gas Study Error")


@router.get("/dashboard/gas-studies")
def gas_studies_page(request: Request):
    try:
        from api.routes_gas import list_studies

        data = list_studies()
        return _render(
            request,
            "gas_studies.html",
            {"title": "Gas Studies", "studies": data.get("studies", [])},
        )
    except Exception as exc:
        return _error(request, str(exc), title="Gas Studies Error", status_code=500)


@router.get("/dashboard/gas-studies/{study_id}")
def gas_study_detail_page(request: Request, study_id: str):
    try:
        import json as _json

        from fastapi import HTTPException as _HTTPException

        from api.routes_gas import _study_dir
        from proof_client.gas_report import compute_merkle_savings, summarize_workflows

        try:
            d = _study_dir(study_id)
        except _HTTPException as exc:
            return _error(
                request, str(exc.detail), title="Not Found",
                status_code=exc.status_code,
            )
        study = _json.loads((d / "gas_study.json").read_text(encoding="utf-8"))
        summaries = summarize_workflows(study.get("records", []))
        savings = compute_merkle_savings(summaries)
        return _render(
            request,
            "gas_report.html",
            {
                "title": f"Gas Study {study_id}",
                "study": study,
                "summaries": summaries,
                "merkle_savings": savings,
            },
        )
    except Exception as exc:
        return _error(request, str(exc), title="Gas Study Error", status_code=500)


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
