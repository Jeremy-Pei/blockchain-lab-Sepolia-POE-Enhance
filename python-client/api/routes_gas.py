"""
routes_gas.py — Gas study endpoints (Stage 13)

GET  /gas/studies                     list gas studies
GET  /gas/studies/{study_id}          full study record + workflow summaries
GET  /gas/studies/{study_id}/report   report file (md / json / csv / pdf)
POST /gas/studies/run                 run a study (requires confirm=true)

SECURITY: POST /gas/studies/run broadcasts multiple on-chain transactions
and spends native tokens. It therefore requires confirm=true.
"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from proof_client.gas_report import compute_merkle_savings, summarize_workflows
from proof_client.gas_study import GAS_STUDIES_DIR

router = APIRouter()

_REPORT_FILES = {
    "md": ("gas_study.md", "text/markdown"),
    "json": ("gas_study.json", "application/json"),
    "csv": ("gas_study.csv", "text/csv"),
    "pdf": ("gas_study_report.pdf", "application/pdf"),
}


class GasStudyRequest(BaseModel):
    network: str
    confirm: bool = False
    dry_run: bool = False
    batch_size: int = 5
    include_ipfs: bool = False
    include_encrypted_ipfs: bool = False
    include_merkle: bool = True
    ipfs_provider: str | None = None
    salt: str | None = None


def _study_dir(study_id: str):
    # Reject path separators so a crafted study_id cannot escape the
    # gas studies directory.
    if "/" in study_id or "\\" in study_id or ".." in study_id:
        raise HTTPException(status_code=400, detail=f"Invalid study id: {study_id!r}")
    d = GAS_STUDIES_DIR / study_id
    if not (d / "gas_study.json").exists():
        raise HTTPException(status_code=404, detail=f"Gas study not found: {study_id!r}")
    return d


@router.get("/studies")
def list_studies():
    """List all gas studies, newest first."""
    studies = []
    if GAS_STUDIES_DIR.exists():
        for d in sorted(GAS_STUDIES_DIR.iterdir(), reverse=True):
            f = d / "gas_study.json"
            if not f.exists():
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            studies.append({
                "study_id": data.get("study_id", d.name),
                "network_key": data.get("network_key", ""),
                "network_display_name": data.get("network_display_name", ""),
                "chain_id": data.get("chain_id", 0),
                "batch_size": data.get("batch_size", 0),
                "workflows": data.get("workflows", []),
                "tx_count": len(data.get("records", [])),
                "created_at_utc": data.get("created_at_utc", ""),
            })
    return {"status": "ok", "count": len(studies), "studies": studies}


@router.get("/studies/{study_id}")
def get_study(study_id: str):
    """Return the full study record plus per-workflow summaries."""
    d = _study_dir(study_id)
    data = json.loads((d / "gas_study.json").read_text(encoding="utf-8"))
    summaries = summarize_workflows(data.get("records", []))
    savings = compute_merkle_savings(summaries)
    return {
        "status": "ok",
        "study": data,
        "summaries": summaries,
        "merkle_savings_percentage": savings,
    }


@router.get("/studies/{study_id}/report")
def get_study_report(study_id: str, format: str = "md"):
    """Download a study report file. format: md | json | csv | pdf."""
    d = _study_dir(study_id)
    if format not in _REPORT_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown format {format!r}; use one of {sorted(_REPORT_FILES)}",
        )
    filename, media_type = _REPORT_FILES[format]
    path = d / filename
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"Report file {filename} not found for {study_id!r}"
        )
    return FileResponse(str(path), media_type=media_type, filename=f"{study_id}_{filename}")


@router.post("/studies/run")
def run_study(req: GasStudyRequest):
    """Run a gas study. Requires confirm=true to broadcast transactions."""
    if not req.dry_run and not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Gas study requires confirm=true because it broadcasts "
                   "on-chain transactions.",
        )

    from proof_client.gas_study import run_gas_study

    try:
        study = run_gas_study(
            network_key=req.network,
            batch_size=req.batch_size,
            include_merkle=req.include_merkle,
            include_ipfs=req.include_ipfs,
            include_encrypted_ipfs=req.include_encrypted_ipfs,
            ipfs_provider=req.ipfs_provider,
            salt=req.salt,
            dry_run=req.dry_run,
        )
    except (ValueError, FileNotFoundError, ConnectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"status": "ok", "study": study}
