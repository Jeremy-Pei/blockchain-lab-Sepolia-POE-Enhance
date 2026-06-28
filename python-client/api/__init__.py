"""
api — Stage 10 FastAPI evidence service.

A thin HTTP layer over the proof_client toolkit. The business logic still
lives in proof_client/; this package only adapts it to REST endpoints.

Run locally:
    cd python-client
    PYTHONPATH=. .venv/bin/uvicorn api.main:app --reload
"""

API_VERSION = "0.10.0"
API_STAGE = "Stage 10"
API_NAME = "FastAPI Evidence Service"
SERVICE_NAME = "proof-of-existence-api"
