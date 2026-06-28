"""
routes_health.py — Liveness and version endpoints.
"""

from fastapi import APIRouter

from api import API_NAME, API_STAGE, API_VERSION, SERVICE_NAME
from api.schemas import HealthResponse, VersionResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return service liveness."""
    return HealthResponse(
        status="ok", service=SERVICE_NAME, version=API_VERSION
    )


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    """Return service version / stage metadata."""
    return VersionResponse(
        status="ok", version=API_VERSION, stage=API_STAGE, name=API_NAME
    )
