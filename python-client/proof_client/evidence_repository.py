"""
evidence_repository.py — SQLite evidence repository

Persists evidence records in a SQLite database for efficient querying
and statistics. Complements evidence_store.py (JSON files):
  - JSON files: for export, sharing, and human readability
  - SQLite database: for efficient querying, statistics, and batch ops
"""

import sqlite3
from pathlib import Path

from proof_client.config import DB_PATH
from proof_client.evidence_schema import EvidenceRecord


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS evidence (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name        TEXT    NOT NULL,
    file_hash        TEXT    NOT NULL UNIQUE,
    uri              TEXT    NOT NULL,
    tx_hash          TEXT    DEFAULT '',
    block_number     INTEGER DEFAULT 0,
    gas_used         INTEGER DEFAULT 0,
    owner            TEXT    DEFAULT '',
    timestamp        INTEGER DEFAULT 0,
    status           TEXT    DEFAULT '',
    network          TEXT    DEFAULT 'Ethereum Sepolia',
    chain_id         INTEGER DEFAULT 11155111,
    contract_address TEXT    DEFAULT '',
    explorer_tx_url  TEXT    DEFAULT '',
    created_at       TEXT    NOT NULL,
    ipfs_cid         TEXT    DEFAULT '',
    ipfs_uri         TEXT    DEFAULT '',
    ipfs_gateway_url TEXT    DEFAULT '',
    ipfs_provider    TEXT    DEFAULT '',
    ipfs_uploaded_at TEXT    DEFAULT '',
    ipfs_sha256      TEXT    DEFAULT '',
    note             TEXT
)
"""

# Columns added after the initial schema; migrated in on existing databases.
_IPFS_COLUMNS = (
    "ipfs_cid",
    "ipfs_uri",
    "ipfs_gateway_url",
    "ipfs_provider",
    "ipfs_uploaded_at",
    "ipfs_sha256",
)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any IPFS columns missing from a pre-Stage-7 database."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(evidence)")}
    for col in _IPFS_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE evidence ADD COLUMN {col} TEXT DEFAULT ''")


def _get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a database connection and ensure the table exists."""
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE_SQL)
    _migrate(conn)
    conn.commit()
    return conn


def insert(record: EvidenceRecord) -> int:
    """
    Insert an evidence record.

    Args:
        record: EvidenceRecord instance.

    Returns:
        Row ID of the inserted row.
    """
    conn = _get_conn()
    d = record.to_dict()
    cols = ", ".join(d.keys())
    placeholders = ", ".join(["?"] * len(d))

    try:
        cur = conn.execute(
            f"INSERT INTO evidence ({cols}) VALUES ({placeholders})",
            list(d.values()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def find_by_hash(file_hash: str) -> EvidenceRecord | None:
    """Find an evidence record by file hash."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM evidence WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        if row is None:
            return None
        return EvidenceRecord.from_dict(dict(row))
    finally:
        conn.close()


def find_all() -> list[EvidenceRecord]:
    """Return all evidence records ordered by id descending."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM evidence ORDER BY id DESC"
        ).fetchall()
        return [EvidenceRecord.from_dict(dict(r)) for r in rows]
    finally:
        conn.close()


def count() -> int:
    """Return the total number of evidence records."""
    conn = _get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    finally:
        conn.close()


def find_by_id(row_id: int) -> EvidenceRecord | None:
    """Find an evidence record by its auto-increment row id."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM evidence WHERE id = ?", (row_id,)
        ).fetchone()
        if row is None:
            return None
        return EvidenceRecord.from_dict(dict(row))
    finally:
        conn.close()


def find_by_owner(owner: str) -> list[EvidenceRecord]:
    """Find evidence records by owner address."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM evidence WHERE owner = ? ORDER BY id DESC",
            (owner,),
        ).fetchall()
        return [EvidenceRecord.from_dict(dict(r)) for r in rows]
    finally:
        conn.close()
