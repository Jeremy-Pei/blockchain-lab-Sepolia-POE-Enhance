"""
schemas.py — Pydantic request/response models for the Stage 10 API.

These models document the API surface (they drive the Swagger schema) and
provide light response validation. Endpoints that return rich, evolving
records (evidence / batch dicts) return plain dicts wrapped in an envelope
rather than over-constraining the shape.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Health ─────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "proof-of-existence-api"
    version: str = "0.10.0"


class VersionResponse(BaseModel):
    status: str = "ok"
    version: str = "0.10.0"
    stage: str = "Stage 10"
    name: str = "FastAPI Evidence Service"


# ── Files ──────────────────────────────────────────────────────────


class HashResponse(BaseModel):
    status: str = "ok"
    file_name: str
    file_size_bytes: int
    file_hash_algorithm: str = "SHA-256"
    file_hash: str
    saved_path: str


# ── Register ───────────────────────────────────────────────────────


class RegisterFileResponse(BaseModel):
    status: str = "ok"
    file_name: str
    file_hash: str
    uri: Optional[str] = None
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    gas_used: Optional[int] = None
    owner: Optional[str] = None
    network: Optional[str] = None
    explorer_url: Optional[str] = None
    evidence_path: Optional[str] = None
    is_encrypted: bool = False
    ipfs_cid: Optional[str] = None
    ipfs_uri: Optional[str] = None
    record: Optional[dict[str, Any]] = None


# ── Verify ─────────────────────────────────────────────────────────


class VerifyResponse(BaseModel):
    status: str = "ok"
    passed: bool
    message: str
    file_hash: Optional[str] = None
    transaction_hash: Optional[str] = None
    details: Optional[dict[str, Any]] = None


# ── Evidence query ─────────────────────────────────────────────────


class EvidenceListResponse(BaseModel):
    status: str = "ok"
    count: int
    records: list[dict[str, Any]]


class EvidenceItemResponse(BaseModel):
    status: str = "ok"
    record: dict[str, Any]


# ── Packages ───────────────────────────────────────────────────────


class PackageExportResponse(BaseModel):
    status: str = "ok"
    file_hash: str
    package_name: str
    package_path: str
    zip_name: str
    zip_path: str


class PackageListResponse(BaseModel):
    status: str = "ok"
    count: int
    packages: list[dict[str, Any]]


# ── Batches ────────────────────────────────────────────────────────


class BatchRegisterResponse(BaseModel):
    status: str = "ok"
    batch_id: str
    file_count: int
    merkle_root: str
    uri: Optional[str] = None
    transaction_hash: Optional[str] = None
    explorer_url: Optional[str] = None
    package_zip: Optional[str] = None
    dry_run: bool = False


# ── Errors ─────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str
    detail: Optional[Any] = Field(
        default=None, description="Optional structured error detail"
    )
