"""
proof_client — Proof-of-Existence Python client toolkit

Modules:
    config              Unified configuration management
    hash_file           SHA-256 file hashing
    wallet              Web3 connection and wallet management
    contract_client     Contract calls (register / verify)
    evidence_schema     Evidence data structure (dataclass)
    evidence_store      Evidence JSON file persistence
    evidence_repository Evidence SQLite database persistence
    register_file       Register a file on-chain
    verify_file         Verify on-chain registration status
    batch_register      Batch registration
    generate_report     Generate Markdown proof report
    query_evidence      Query evidence records
"""

__version__ = "0.1.0"
