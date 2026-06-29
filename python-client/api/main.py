"""
main.py — Stage 10 FastAPI application factory.

Wires every router under the application and installs a unified error
envelope so failures consistently return ``{"status": "error", ...}``.

Run locally:
    cd python-client
    PYTHONPATH=. .venv/bin/uvicorn api.main:app --reload

Then open http://127.0.0.1:8000/docs

SECURITY: This service is intended for LOCAL development only. It can sign
on-chain transactions using the private key in .env, read local files, and
accept encryption passwords. Do NOT expose it to the public internet without
adding authentication, rate limiting, input validation, and key-management
hardening. See docs/stage10_fastapi_service.md.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api import API_NAME, API_VERSION
from api.routes_batches import router as batches_router
from api.routes_dashboard import router as dashboard_router
from api.routes_evidence import router as evidence_router
from api.routes_files import router as files_router
from api.routes_health import router as health_router
from api.routes_packages import router as packages_router
from api.routes_register import router as register_router
from api.routes_verify import router as verify_router

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(
    title="Proof-of-Existence Evidence API",
    description=(
        "FastAPI service for blockchain-based proof-of-existence evidence "
        "workflows. Wraps the proof_client CLI toolkit (hashing, registration, "
        "verification, evidence query, package export, Merkle batches) as a "
        "local HTTP API.\n\n"
        "**Security:** intended for local development only; do not expose "
        "publicly without authentication and key-management hardening."
    ),
    version=API_VERSION,
    contact={"name": API_NAME},
)


# ── Unified error envelope ─────────────────────────────────────────


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Wrap HTTPExceptions in the standard {status: error, message} envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Wrap request-validation errors (422) in the standard envelope."""
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "Request validation failed",
            "detail": jsonable_encoder(exc.errors()),
        },
    )


# ── Static files ───────────────────────────────────────────────────

app.mount(
    "/static",
    StaticFiles(directory=str(_WEB_DIR / "static")),
    name="static",
)

# ── Routers ────────────────────────────────────────────────────────

app.include_router(dashboard_router, tags=["Dashboard"])
app.include_router(health_router, prefix="", tags=["Health"])
app.include_router(files_router, prefix="/files", tags=["Files"])
app.include_router(evidence_router, prefix="/evidence", tags=["Evidence"])
app.include_router(register_router, prefix="/register", tags=["Register"])
app.include_router(verify_router, prefix="/verify", tags=["Verify"])
app.include_router(packages_router, prefix="/packages", tags=["Packages"])
app.include_router(batches_router, prefix="/batches", tags=["Batches"])
