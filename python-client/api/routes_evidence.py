"""
routes_evidence.py — Read-only evidence query endpoints.

Paths are namespaced (/files, /batches, /tx) to avoid collisions between the
list endpoints and the by-identifier lookups.
"""

from fastapi import APIRouter, HTTPException

from api import services

router = APIRouter()


@router.get("/files")
def get_evidence_files(limit: int = 20):
    """List the most recent single-file evidence records."""
    return services.list_evidence_files(limit=limit)


@router.get("/files/{file_hash}")
def get_evidence_by_hash(file_hash: str):
    """Return a single evidence record by file hash."""
    record = services.get_evidence_by_hash(file_hash)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return {"status": "ok", "record": record}


@router.get("/tx/{transaction_hash}")
def get_evidence_by_tx(transaction_hash: str):
    """Return a single evidence record by transaction hash."""
    record = services.get_evidence_by_tx(transaction_hash)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence not found for transaction")
    return {"status": "ok", "record": record}


@router.get("/batches")
def get_batches(limit: int = 20):
    """List the most recent batch Merkle evidence records."""
    return services.list_batch_records(limit=limit)


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str):
    """Return a single batch evidence record by batch_id."""
    record = services.get_batch_record(batch_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Batch evidence not found")
    return {"status": "ok", "record": record}
