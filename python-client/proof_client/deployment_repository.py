"""
deployment_repository.py — SQLite repository for contract deployments (Stage 13)

Persists DeploymentRecord rows so that:
  - deployment history can be listed per network
  - the latest deployed contract address can be resolved automatically
    (used by network_context.resolve_contract_address when the env var
    for a network's contract address is not set)
"""

import sqlite3
from pathlib import Path

from proof_client.config import DB_PATH
from proof_client.deployment_record import DeploymentRecord


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS deployment_records (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type             TEXT    DEFAULT 'contract_deployment',
    contract_name           TEXT    NOT NULL,
    network_key             TEXT    NOT NULL,
    network_display_name    TEXT    DEFAULT '',
    chain_id                INTEGER NOT NULL,
    contract_address        TEXT    NOT NULL,
    deployer_address        TEXT    DEFAULT '',
    transaction_hash        TEXT    DEFAULT '',
    block_number            INTEGER DEFAULT 0,
    block_timestamp         INTEGER DEFAULT 0,
    gas_used                INTEGER DEFAULT 0,
    effective_gas_price_wei INTEGER DEFAULT 0,
    deployment_fee_wei      INTEGER DEFAULT 0,
    deployment_fee_eth      TEXT    DEFAULT '',
    explorer_url            TEXT    DEFAULT '',
    artifact_path           TEXT    DEFAULT '',
    created_at_utc          TEXT    NOT NULL
)
"""


def _get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a database connection and ensure the table exists."""
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()
    return conn


def init_deployment_db(db_path: Path | None = None) -> None:
    """Create the deployment_records table if it does not exist."""
    conn = _get_conn(db_path)
    conn.close()


def save_deployment_record(
    record: DeploymentRecord, db_path: Path | None = None
) -> int:
    """Insert a deployment record and return its row id."""
    conn = _get_conn(db_path)
    d = record.to_dict()
    cols = ", ".join(d.keys())
    placeholders = ", ".join(["?"] * len(d))
    try:
        cur = conn.execute(
            f"INSERT INTO deployment_records ({cols}) VALUES ({placeholders})",
            list(d.values()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_deployment_records(
    network_key: str | None = None, db_path: Path | None = None
) -> list[DeploymentRecord]:
    """Return deployment records, newest first, optionally filtered by network."""
    conn = _get_conn(db_path)
    try:
        if network_key:
            rows = conn.execute(
                "SELECT * FROM deployment_records WHERE network_key = ? "
                "ORDER BY id DESC",
                (network_key,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM deployment_records ORDER BY id DESC"
            ).fetchall()
        return [DeploymentRecord.from_dict(dict(r)) for r in rows]
    finally:
        conn.close()


def get_latest_deployment(
    network_key: str,
    contract_name: str = "ProofOfExistence",
    db_path: Path | None = None,
) -> DeploymentRecord | None:
    """Return the most recent deployment for a network + contract, or None."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM deployment_records "
            "WHERE network_key = ? AND contract_name = ? "
            "ORDER BY id DESC LIMIT 1",
            (network_key, contract_name),
        ).fetchone()
        if row is None:
            return None
        return DeploymentRecord.from_dict(dict(row))
    finally:
        conn.close()
