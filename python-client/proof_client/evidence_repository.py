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
    is_encrypted                INTEGER DEFAULT 0,
    encryption_algorithm        TEXT    DEFAULT '',
    encryption_kdf              TEXT    DEFAULT '',
    encryption_kdf_iterations   INTEGER DEFAULT 0,
    encryption_salt_hex         TEXT    DEFAULT '',
    encryption_nonce_hex        TEXT    DEFAULT '',
    encrypted_file_hash         TEXT    DEFAULT '',
    encrypted_file_name         TEXT    DEFAULT '',
    encrypted_ipfs_cid          TEXT    DEFAULT '',
    encrypted_ipfs_uri          TEXT    DEFAULT '',
    encrypted_ipfs_gateway_url  TEXT    DEFAULT '',
    encrypted_ipfs_provider     TEXT    DEFAULT '',
    encrypted_ipfs_uploaded_at  TEXT    DEFAULT '',
    note             TEXT
)
"""

# Columns added after the initial schema; migrated in on existing databases.
# Each entry is (column_name, column_definition).
_IPFS_COLUMNS = (
    ("ipfs_cid", "TEXT DEFAULT ''"),
    ("ipfs_uri", "TEXT DEFAULT ''"),
    ("ipfs_gateway_url", "TEXT DEFAULT ''"),
    ("ipfs_provider", "TEXT DEFAULT ''"),
    ("ipfs_uploaded_at", "TEXT DEFAULT ''"),
    ("ipfs_sha256", "TEXT DEFAULT ''"),
)

# Stage 8 encryption columns (migrated in on existing databases).
_ENCRYPTION_COLUMNS = (
    ("is_encrypted", "INTEGER DEFAULT 0"),
    ("encryption_algorithm", "TEXT DEFAULT ''"),
    ("encryption_kdf", "TEXT DEFAULT ''"),
    ("encryption_kdf_iterations", "INTEGER DEFAULT 0"),
    ("encryption_salt_hex", "TEXT DEFAULT ''"),
    ("encryption_nonce_hex", "TEXT DEFAULT ''"),
    ("encrypted_file_hash", "TEXT DEFAULT ''"),
    ("encrypted_file_name", "TEXT DEFAULT ''"),
    ("encrypted_ipfs_cid", "TEXT DEFAULT ''"),
    ("encrypted_ipfs_uri", "TEXT DEFAULT ''"),
    ("encrypted_ipfs_gateway_url", "TEXT DEFAULT ''"),
    ("encrypted_ipfs_provider", "TEXT DEFAULT ''"),
    ("encrypted_ipfs_uploaded_at", "TEXT DEFAULT ''"),
)

# Stage 12 multi-network columns (migrated in on existing databases).
_NETWORK_COLUMNS = (
    ("network_key", "TEXT DEFAULT ''"),
    ("explorer_base_url", "TEXT DEFAULT ''"),
)

# Stage 13 gas cost columns (migrated in on existing databases).
_GAS_COLUMNS = (
    ("effective_gas_price_wei", "INTEGER DEFAULT 0"),
    ("total_fee_wei", "INTEGER DEFAULT 0"),
    ("total_fee_eth", "TEXT DEFAULT ''"),
    ("native_token_symbol", "TEXT DEFAULT ''"),
)


def ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_def: str,
) -> None:
    """Add a column to a table if it does not already exist (idempotent).

    A reusable migration primitive so each new stage can add columns without
    re-implementing the PRAGMA dance.
    """
    existing = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")
    }
    if column_name not in existing:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"
        )


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any columns missing from a pre-Stage-7/8/12/13 database."""
    for col, col_def in (
        *_IPFS_COLUMNS, *_ENCRYPTION_COLUMNS, *_NETWORK_COLUMNS, *_GAS_COLUMNS
    ):
        ensure_column(conn, "evidence", col, col_def)


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


# ── Stage 9: Batch Merkle evidence table ──────────────────────────

_CREATE_BATCH_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS batch_evidence_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id            TEXT    NOT NULL UNIQUE,
    batch_title         TEXT    DEFAULT '',
    author              TEXT    DEFAULT '',
    description         TEXT    DEFAULT '',
    file_count          INTEGER DEFAULT 0,
    merkle_root         TEXT    NOT NULL UNIQUE,
    uri                 TEXT    DEFAULT '',
    network             TEXT    DEFAULT 'Ethereum Sepolia',
    chain_id            INTEGER DEFAULT 11155111,
    contract_address    TEXT    DEFAULT '',
    owner_address       TEXT    DEFAULT '',
    transaction_hash    TEXT    DEFAULT '' UNIQUE,
    block_number        INTEGER DEFAULT 0,
    block_timestamp     INTEGER DEFAULT 0,
    explorer_url        TEXT    DEFAULT '',
    batch_evidence_json TEXT    DEFAULT '',
    created_at_utc      TEXT    NOT NULL
)
"""


_BATCH_NETWORK_COLUMNS = (
    ("network_key", "TEXT DEFAULT ''"),
    ("explorer_base_url", "TEXT DEFAULT ''"),
)

# Stage 13 gas cost columns for batch records.
_BATCH_GAS_COLUMNS = (
    ("gas_used", "INTEGER DEFAULT 0"),
    ("effective_gas_price_wei", "INTEGER DEFAULT 0"),
    ("total_fee_wei", "INTEGER DEFAULT 0"),
    ("total_fee_eth", "TEXT DEFAULT ''"),
    ("cost_per_file_wei", "INTEGER DEFAULT 0"),
    ("cost_per_file_eth", "TEXT DEFAULT ''"),
    ("native_token_symbol", "TEXT DEFAULT ''"),
)


def _migrate_batch(conn: sqlite3.Connection) -> None:
    """Add Stage 12/13 columns to batch_evidence_records if missing."""
    for col, col_def in (*_BATCH_NETWORK_COLUMNS, *_BATCH_GAS_COLUMNS):
        ensure_column(conn, "batch_evidence_records", col, col_def)


def _get_batch_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a database connection and ensure the batch table exists."""
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE_SQL)
    _migrate(conn)
    conn.execute(_CREATE_BATCH_TABLE_SQL)
    _migrate_batch(conn)
    conn.commit()
    return conn


def insert_batch_evidence(evidence: dict, db_path: Path | None = None) -> int:
    """
    Insert a batch evidence record.

    Args:
        evidence: Dict matching the batch_evidence_records schema.
        db_path: Optional override for the database path (used in tests).

    Returns:
        Row ID of the inserted row.
    """
    conn = _get_batch_conn(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO batch_evidence_records (
                batch_id, batch_title, author, description, file_count,
                merkle_root, uri, network, chain_id, contract_address,
                owner_address, transaction_hash, block_number, block_timestamp,
                explorer_url, batch_evidence_json, created_at_utc,
                network_key, explorer_base_url,
                gas_used, effective_gas_price_wei, total_fee_wei, total_fee_eth,
                cost_per_file_wei, cost_per_file_eth, native_token_symbol
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence.get("batch_id", ""),
                evidence.get("batch_title", ""),
                evidence.get("author", ""),
                evidence.get("description", ""),
                evidence.get("file_count", 0),
                evidence.get("merkle_root", ""),
                evidence.get("uri", ""),
                evidence.get("network", "Ethereum Sepolia"),
                evidence.get("chain_id", 11155111),
                evidence.get("contract_address", ""),
                evidence.get("owner_address", ""),
                evidence.get("transaction_hash", ""),
                evidence.get("block_number", 0),
                evidence.get("block_timestamp", 0),
                evidence.get("explorer_url", ""),
                evidence.get("batch_evidence_json", ""),
                evidence.get("created_at_utc", ""),
                evidence.get("network_key", ""),
                evidence.get("explorer_base_url", ""),
                evidence.get("gas_used", 0),
                evidence.get("effective_gas_price_wei", 0),
                evidence.get("total_fee_wei", 0),
                evidence.get("total_fee_eth", ""),
                evidence.get("cost_per_file_wei", 0),
                evidence.get("cost_per_file_eth", ""),
                evidence.get("native_token_symbol", ""),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def find_batch_by_id(batch_id: str, db_path: Path | None = None) -> dict | None:
    """Find a batch evidence record by batch_id."""
    conn = _get_batch_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM batch_evidence_records WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_batch_by_merkle_root(merkle_root: str, db_path: Path | None = None) -> dict | None:
    """Find a batch evidence record by its Merkle root."""
    conn = _get_batch_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM batch_evidence_records WHERE merkle_root = ?", (merkle_root,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_batches(limit: int = 20, db_path: Path | None = None) -> list[dict]:
    """Return the most recent batch evidence records."""
    conn = _get_batch_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM batch_evidence_records ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
