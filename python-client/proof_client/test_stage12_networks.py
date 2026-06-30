"""
test_stage12_networks.py — Stage 12 test suite (multi-network evidence support)

Tests:
  1.  Network config loading (JSON files)
  2.  Key normalisation (hyphen → underscore)
  3.  Default network resolution
  4.  Env-var property resolution
  5.  Explorer URL generation
  6.  Network context chain-ID validation
  7.  Evidence schema multi-network fields
  8.  Evidence repository migration
  9.  Batch evidence multi-network fields
  10. CLI --network flag integration (mocked)
  11. Backward compatibility

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m proof_client.test_stage12_networks
"""

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# ══════════════════════════════════════════════════════════════════
# Test helpers
# ══════════════════════════════════════════════════════════════════

_passed = 0
_failed = 0


def ok(name: str, detail: str = ""):
    global _passed
    _passed += 1
    suffix = f" → {detail}" if detail else ""
    print(f"  ✅ {name}{suffix}")


def fail(name: str, err: str):
    global _failed
    _failed += 1
    print(f"  ❌ {name} → {err}")


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        ok(name, detail)
    else:
        fail(name, detail or "assertion failed")


def section(title: str):
    print(f"\n{'━'*60}")
    print(f"  🌐 {title}")
    print(f"{'━'*60}")


# ══════════════════════════════════════════════════════════════════
# 1. Network config loading
# ══════════════════════════════════════════════════════════════════


def test_network_config_loading():
    section("Network Config Loading")
    from proof_client.network_config import load_network_config, NETWORKS_DIR

    check("T01 networks/ dir exists", NETWORKS_DIR.is_dir())

    cfg = load_network_config("sepolia")
    check("T02 load sepolia config", cfg is not None)
    check("T03 sepolia network_key", cfg.network_key == "sepolia")
    check("T04 sepolia display_name", cfg.display_name == "Ethereum Sepolia")
    check("T05 sepolia chain_id", cfg.chain_id == 11155111)
    check("T06 sepolia is_testnet", cfg.is_testnet is True)
    check("T07 sepolia native_token_symbol", cfg.native_token_symbol == "ETH")
    check("T08 sepolia rpc_url_env_key", cfg.rpc_url_env_key == "SEPOLIA_RPC_URL")
    check("T09 sepolia contract_address_env_key", cfg.contract_address_env_key == "SEPOLIA_CONTRACT_ADDRESS")
    check("T10 sepolia enabled", cfg.enabled is True)
    check("T11 sepolia explorer_base_url", "etherscan" in cfg.explorer_base_url)

    cfg_anvil = load_network_config("anvil")
    check("T12 load anvil config", cfg_anvil is not None)
    check("T13 anvil chain_id 31337", cfg_anvil.chain_id == 31337)
    check("T14 anvil explorer_base_url empty", cfg_anvil.explorer_base_url == "")

    cfg_base = load_network_config("base_sepolia")
    check("T15 load base_sepolia config", cfg_base is not None)
    check("T16 base_sepolia chain_id 84532", cfg_base.chain_id == 84532)
    check("T17 base_sepolia display_name", cfg_base.display_name == "Base Sepolia")
    check("T18 base_sepolia explorer contains basescan", "basescan" in cfg_base.explorer_base_url)


# ══════════════════════════════════════════════════════════════════
# 2. Key normalisation
# ══════════════════════════════════════════════════════════════════


def test_key_normalisation():
    section("Key Normalisation")
    from proof_client.network_config import normalize_network_key, load_network_config

    check("T19 hyphen base-sepolia → base_sepolia",
          normalize_network_key("base-sepolia") == "base_sepolia")
    check("T20 uppercase SEPOLIA → sepolia",
          normalize_network_key("SEPOLIA") == "sepolia")
    check("T21 mixed Sepolia → sepolia",
          normalize_network_key("Sepolia") == "sepolia")
    check("T22 trailing spaces stripped",
          normalize_network_key("  sepolia  ") == "sepolia")

    cfg = load_network_config("base-sepolia")
    check("T23 base-sepolia loads base_sepolia.json", cfg.network_key == "base_sepolia")

    try:
        load_network_config("unknown_xyz_network")
        fail("T24 unknown network raises ValueError", "did not raise")
    except ValueError:
        ok("T24 unknown network raises ValueError")


# ══════════════════════════════════════════════════════════════════
# 3. Default network resolution
# ══════════════════════════════════════════════════════════════════


def test_default_network():
    section("Default Network Resolution")
    from proof_client.network_config import get_default_network_key, get_default_network_config

    original = os.environ.get("DEFAULT_NETWORK")
    try:
        os.environ["DEFAULT_NETWORK"] = "sepolia"
        check("T25 DEFAULT_NETWORK=sepolia → sepolia", get_default_network_key() == "sepolia")

        os.environ["DEFAULT_NETWORK"] = "anvil"
        check("T26 DEFAULT_NETWORK=anvil → anvil", get_default_network_key() == "anvil")

        os.environ["DEFAULT_NETWORK"] = "base-sepolia"
        check("T27 DEFAULT_NETWORK=base-sepolia normalises", get_default_network_key() == "base_sepolia")

        del os.environ["DEFAULT_NETWORK"]
        check("T28 no DEFAULT_NETWORK → sepolia", get_default_network_key() == "sepolia")

        os.environ["DEFAULT_NETWORK"] = "sepolia"
        cfg = get_default_network_config()
        check("T29 get_default_network_config returns sepolia", cfg.network_key == "sepolia")
    finally:
        if original is not None:
            os.environ["DEFAULT_NETWORK"] = original
        elif "DEFAULT_NETWORK" in os.environ:
            del os.environ["DEFAULT_NETWORK"]


# ══════════════════════════════════════════════════════════════════
# 4. Env-var property resolution
# ══════════════════════════════════════════════════════════════════


def test_env_var_resolution():
    section("Env-Var Property Resolution")
    from proof_client.network_config import load_network_config

    cfg = load_network_config("sepolia")

    # rpc_url resolves from env
    original_rpc = os.environ.get("SEPOLIA_RPC_URL")
    original_addr = os.environ.get("SEPOLIA_CONTRACT_ADDRESS")
    try:
        os.environ["SEPOLIA_RPC_URL"] = "https://my-rpc.example.com"
        check("T30 rpc_url resolved from env", cfg.rpc_url == "https://my-rpc.example.com")

        del os.environ["SEPOLIA_RPC_URL"]
        check("T31 missing rpc_url env → empty string", cfg.rpc_url == "")

        os.environ["SEPOLIA_CONTRACT_ADDRESS"] = "0xDEAD"
        check("T32 contract_address resolved from env", cfg.contract_address == "0xDEAD")

        del os.environ["SEPOLIA_CONTRACT_ADDRESS"]
        check("T33 missing contract env → empty string", cfg.contract_address == "")
    finally:
        if original_rpc is not None:
            os.environ["SEPOLIA_RPC_URL"] = original_rpc
        elif "SEPOLIA_RPC_URL" in os.environ:
            del os.environ["SEPOLIA_RPC_URL"]
        if original_addr is not None:
            os.environ["SEPOLIA_CONTRACT_ADDRESS"] = original_addr
        elif "SEPOLIA_CONTRACT_ADDRESS" in os.environ:
            del os.environ["SEPOLIA_CONTRACT_ADDRESS"]


# ══════════════════════════════════════════════════════════════════
# 5. Explorer URL generation
# ══════════════════════════════════════════════════════════════════


def test_explorer_urls():
    section("Explorer URL Generation")
    from proof_client.network_config import load_network_config

    cfg_sepolia = load_network_config("sepolia")
    tx = "0xdeadbeef" * 8
    url = cfg_sepolia.tx_url(tx)
    check("T34 sepolia tx_url contains tx hash", tx in url)
    check("T35 sepolia tx_url contains etherscan", "etherscan" in url)

    addr = "0x000000000000000000000000000000000000dEaD"
    addr_url = cfg_sepolia.address_url(addr)
    check("T36 sepolia address_url contains address", addr in addr_url)
    check("T37 sepolia address_url contains etherscan", "etherscan" in addr_url)

    cfg_anvil = load_network_config("anvil")
    check("T38 anvil tx_url returns empty string", cfg_anvil.tx_url(tx) == "")
    check("T39 anvil address_url returns empty string", cfg_anvil.address_url(addr) == "")

    cfg_base = load_network_config("base_sepolia")
    url_base = cfg_base.tx_url(tx)
    check("T40 base_sepolia tx_url contains basescan", "basescan" in url_base)

    # Hash without 0x prefix should be handled
    tx_bare = tx.lstrip("0x")
    url2 = cfg_sepolia.tx_url(tx_bare)
    check("T41 tx_url adds 0x prefix if missing", "0x" in url2)


# ══════════════════════════════════════════════════════════════════
# 6. Network config list
# ══════════════════════════════════════════════════════════════════


def test_list_networks():
    section("List Network Configs")
    from proof_client.network_config import list_network_configs

    configs = list_network_configs()
    check("T42 list_network_configs returns non-empty list", len(configs) > 0)

    keys = [c.network_key for c in configs]
    check("T43 sepolia in configs", "sepolia" in keys)
    check("T44 anvil in configs", "anvil" in keys)
    check("T45 base_sepolia in configs", "base_sepolia" in keys)

    # All returned configs should be enabled
    check("T46 all listed configs are enabled", all(c.enabled for c in configs))


# ══════════════════════════════════════════════════════════════════
# 7. Evidence schema multi-network fields
# ══════════════════════════════════════════════════════════════════


def test_evidence_schema_network_fields():
    section("Evidence Schema Multi-Network Fields")
    from proof_client.evidence_schema import EvidenceRecord

    # Default values for Stage 12 fields
    r = EvidenceRecord(file_name="a.txt", file_hash="0xaa", uri="x")
    check("T47 EvidenceRecord has network_key field", hasattr(r, "network_key"))
    check("T48 EvidenceRecord has explorer_base_url field", hasattr(r, "explorer_base_url"))
    check("T49 network_key default is empty string", r.network_key == "")
    check("T50 explorer_base_url default is empty string", r.explorer_base_url == "")

    # Can be set
    r2 = EvidenceRecord(
        file_name="b.txt",
        file_hash="0xbb",
        uri="y",
        network="Ethereum Sepolia",
        chain_id=11155111,
        network_key="sepolia",
        explorer_base_url="https://sepolia.etherscan.io",
    )
    check("T51 network_key is stored", r2.network_key == "sepolia")
    check("T52 explorer_base_url is stored", "etherscan" in r2.explorer_base_url)

    # Serialises to dict
    d = r2.to_dict()
    check("T53 network_key in dict", "network_key" in d)
    check("T54 explorer_base_url in dict", "explorer_base_url" in d)

    # Deserialises cleanly from dict (old records without new fields)
    old_dict = {"file_name": "c.txt", "file_hash": "0xcc", "uri": "z"}
    r3 = EvidenceRecord.from_dict(old_dict)
    check("T55 old record without network_key deserialises", r3.network_key == "")
    check("T56 old record without explorer_base_url deserialises", r3.explorer_base_url == "")


# ══════════════════════════════════════════════════════════════════
# 8. Evidence repository migration
# ══════════════════════════════════════════════════════════════════


def test_evidence_repository_migration():
    section("Evidence Repository Migration")

    import proof_client.evidence_repository as repo_mod
    from proof_client.evidence_schema import EvidenceRecord

    tmp = Path(tempfile.mkdtemp(prefix="stage12_repo_"))
    db_path = tmp / "test_migration.db"

    # Create an old-style DB without Stage 12 columns
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE evidence (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name        TEXT NOT NULL,
            file_hash        TEXT NOT NULL UNIQUE,
            uri              TEXT NOT NULL,
            tx_hash          TEXT DEFAULT '',
            block_number     INTEGER DEFAULT 0,
            gas_used         INTEGER DEFAULT 0,
            owner            TEXT DEFAULT '',
            timestamp        INTEGER DEFAULT 0,
            status           TEXT DEFAULT '',
            network          TEXT DEFAULT 'Ethereum Sepolia',
            chain_id         INTEGER DEFAULT 11155111,
            contract_address TEXT DEFAULT '',
            explorer_tx_url  TEXT DEFAULT '',
            created_at       TEXT NOT NULL
        )
    """)
    conn.execute("INSERT INTO evidence (file_name, file_hash, uri, created_at) VALUES (?, ?, ?, ?)",
                 ("old.txt", "0xold123", "x://old", "2024-01-01T00:00:00+00:00"))
    conn.commit()
    conn.close()

    # Now open with the repository (should auto-migrate)
    conn2 = repo_mod._get_conn(db_path)

    cols = {row["name"] for row in conn2.execute("PRAGMA table_info(evidence)")}
    check("T57 network_key column added by migration", "network_key" in cols)
    check("T58 explorer_base_url column added by migration", "explorer_base_url" in cols)

    # Existing row is still readable after migration
    row = conn2.execute("SELECT * FROM evidence WHERE file_hash = '0xold123'").fetchone()
    check("T59 existing row readable after migration", row is not None)
    check("T60 network_key defaults to empty string", row["network_key"] == "")
    conn2.close()


# ══════════════════════════════════════════════════════════════════
# 9. Batch evidence multi-network fields
# ══════════════════════════════════════════════════════════════════


def test_batch_evidence_network_fields():
    section("Batch Evidence Multi-Network Fields")
    from proof_client.merkle_evidence import BatchEvidence

    be = BatchEvidence()
    check("T61 BatchEvidence has network_key field", hasattr(be, "network_key"))
    check("T62 BatchEvidence has explorer_base_url field", hasattr(be, "explorer_base_url"))
    check("T63 BatchEvidence network_key default empty", be.network_key == "")
    check("T64 BatchEvidence explorer_base_url default empty", be.explorer_base_url == "")

    be2 = BatchEvidence(
        batch_id="batch-test",
        network="Base Sepolia",
        chain_id=84532,
        network_key="base_sepolia",
        explorer_base_url="https://sepolia.basescan.org",
    )
    check("T65 BatchEvidence network_key stored", be2.network_key == "base_sepolia")
    check("T66 BatchEvidence explorer_base_url stored", "basescan" in be2.explorer_base_url)

    d = be2.to_dict()
    check("T67 network_key in BatchEvidence dict", "network_key" in d)
    check("T68 explorer_base_url in BatchEvidence dict", "explorer_base_url" in d)


# ══════════════════════════════════════════════════════════════════
# 10. Batch evidence repo migration
# ══════════════════════════════════════════════════════════════════


def test_batch_repo_migration():
    section("Batch Evidence Repository Migration")
    import proof_client.evidence_repository as repo_mod

    tmp = Path(tempfile.mkdtemp(prefix="stage12_batch_"))
    db_path = tmp / "batch_mig.db"

    # Old batch table without Stage 12 columns
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL, file_hash TEXT NOT NULL UNIQUE,
            uri TEXT NOT NULL, created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE batch_evidence_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL UNIQUE,
            merkle_root TEXT NOT NULL UNIQUE,
            network TEXT DEFAULT 'Ethereum Sepolia',
            chain_id INTEGER DEFAULT 11155111,
            contract_address TEXT DEFAULT '',
            owner_address TEXT DEFAULT '',
            transaction_hash TEXT DEFAULT '' UNIQUE,
            block_number INTEGER DEFAULT 0,
            block_timestamp INTEGER DEFAULT 0,
            explorer_url TEXT DEFAULT '',
            batch_evidence_json TEXT DEFAULT '',
            created_at_utc TEXT NOT NULL
        )
    """)
    conn.execute("INSERT INTO batch_evidence_records (batch_id, merkle_root, created_at_utc) VALUES (?, ?, ?)",
                 ("batch-old", "0xoldroot", "2024-01-01T00:00:00Z"))
    conn.commit()
    conn.close()

    conn2 = repo_mod._get_batch_conn(db_path)
    cols = {row["name"] for row in conn2.execute("PRAGMA table_info(batch_evidence_records)")}
    check("T69 batch network_key column added", "network_key" in cols)
    check("T70 batch explorer_base_url column added", "explorer_base_url" in cols)

    row = conn2.execute("SELECT * FROM batch_evidence_records WHERE batch_id='batch-old'").fetchone()
    check("T71 old batch row readable after migration", row is not None)
    check("T72 old batch network_key defaults to empty", row["network_key"] == "")
    conn2.close()


# ══════════════════════════════════════════════════════════════════
# 11. Proof JSON includes network_key
# ══════════════════════════════════════════════════════════════════


def test_proof_json_network():
    section("Proof JSON Network Fields")
    from proof_client.merkle_evidence import (
        MerkleLeaf, BatchEvidence, write_proof_json
    )

    tmp = Path(tempfile.mkdtemp(prefix="stage12_proof_"))
    proofs_dir = tmp / "proofs"
    proofs_dir.mkdir()

    leaf = MerkleLeaf(
        index=0,
        relative_path="a.txt",
        file_name="a.txt",
        file_size_bytes=5,
        file_hash="0x" + "aa" * 32,
    )
    batch_evidence = BatchEvidence(
        batch_id="batch-net-test",
        network="Base Sepolia",
        chain_id=84532,
        contract_address="0xCONTRACT",
        network_key="base_sepolia",
        explorer_base_url="https://sepolia.basescan.org",
        merkle_root="0x" + "bb" * 32,
        transaction_hash="0x" + "cc" * 32,
        explorer_url="https://sepolia.basescan.org/tx/0x" + "cc" * 32,
    )

    path = write_proof_json(
        proofs_dir=proofs_dir,
        leaf=leaf,
        merkle_root=batch_evidence.merkle_root,
        batch_id="batch-net-test",
        leaf_hashes=["0x" + "aa" * 32],
        evidence=batch_evidence,
    )

    proof = json.loads(path.read_text())
    check("T73 proof JSON has network_key", proof.get("network_key") == "base_sepolia")
    check("T74 proof JSON has network", proof.get("network") == "Base Sepolia")
    check("T75 proof JSON has chain_id", proof.get("chain_id") == 84532)
    check("T76 proof JSON has contract_address", "0xCONTRACT" in proof.get("contract_address", ""))


# ══════════════════════════════════════════════════════════════════
# 12. CLI --network flag (mocked blockchain calls)
# ══════════════════════════════════════════════════════════════════


def test_cli_network_flag():
    section("CLI --network Flag")
    from proof_client.register_file import _parse_args

    args = _parse_args(["works/paper.pdf", "--network", "base-sepolia"])
    check("T77 --network accepted in register CLI", args.network == "base-sepolia")

    args2 = _parse_args(["works/paper.pdf"])
    check("T78 no --network defaults to None", args2.network is None)

    from proof_client.verify_file import _parse_args as v_parse
    args3 = v_parse(["works/paper.pdf", "--network", "anvil"])
    check("T79 --network accepted in verify CLI", args3.network == "anvil")

    from proof_client.batch_merkle_register import _parse_args as b_parse
    args4 = b_parse(["works/", "--network", "sepolia", "--dry-run"])
    check("T80 --network accepted in batch CLI", args4.network == "sepolia")

    from proof_client.verify_merkle_proof import _parse_args as vm_parse
    args5 = vm_parse(["--file", "f.txt", "--proof", "p.json", "--network", "base_sepolia"])
    check("T81 --network accepted in verify_merkle CLI", args5.network == "base_sepolia")


# ══════════════════════════════════════════════════════════════════
# 13. register_file stores network info in evidence record
# ══════════════════════════════════════════════════════════════════


def test_register_file_network_integration():
    section("Register File Network Integration")

    import proof_client.register_file as reg_mod
    import proof_client.evidence_repository as repo_mod
    import proof_client.evidence_store as store_mod

    tmp = Path(tempfile.mkdtemp(prefix="stage12_reg_"))
    repo_mod.DB_PATH = tmp / "test.db"
    store_mod.EVIDENCE_DIR = tmp / "evidence"
    store_mod.EVIDENCE_DIR.mkdir()

    # Prepare a test file
    test_file = tmp / "test.txt"
    test_file.write_bytes(b"stage 12 test content")

    _MOCK_TX = {
        "tx_hash": "aa" * 32,
        "block_number": 1,
        "gas_used": 21000,
        "status": "success",
        "contract_address": "0xMOCKCONTRACT",
        "network_key": "sepolia",
    }

    # Patch the blockchain seam
    original_rh = reg_mod.register_hash
    original_ga = reg_mod.get_address
    try:
        reg_mod.register_hash = lambda fh, uri, network_key=None: dict(_MOCK_TX)
        reg_mod.get_address = lambda: "0xDEAD"

        record = reg_mod.register_file(str(test_file), network_key="sepolia")

        check("T82 register_file returns EvidenceRecord", record is not None)
        check("T83 network_key stored in record", record.network_key == "sepolia")
        check("T84 network display name stored", "Sepolia" in record.network)
        check("T85 chain_id 11155111 stored", record.chain_id == 11155111)
        check("T86 explorer_base_url stored", "etherscan" in record.explorer_base_url)
        check("T87 URI uses network key prefix", record.uri.startswith("sepolia://"))
    finally:
        reg_mod.register_hash = original_rh
        reg_mod.get_address = original_ga


# ══════════════════════════════════════════════════════════════════
# 14. Backward compatibility
# ══════════════════════════════════════════════════════════════════


def test_backward_compatibility():
    section("Backward Compatibility")
    from proof_client.evidence_schema import EvidenceRecord
    import inspect
    from proof_client import register_file as reg_mod
    from proof_client import verify_file as ver_mod
    from proof_client import batch_merkle_register as batch_mod

    # Old evidence JSON without Stage 12 fields still loads
    old_json = {
        "file_name": "old.txt",
        "file_hash": "0xold",
        "uri": "sepolia://old.txt",
        "network": "Ethereum Sepolia",
        "chain_id": 11155111,
    }
    rec = EvidenceRecord.from_dict(old_json)
    check("T88 old evidence JSON deserialises without network_key", rec.network_key == "")

    # register_file signature accepts network_key
    sig = inspect.signature(reg_mod.register_file)
    check("T89 register_file has network_key param", "network_key" in sig.parameters)

    # verify_file signature accepts network_key
    sig_v = inspect.signature(ver_mod.verify_file)
    check("T90 verify_file has network_key param", "network_key" in sig_v.parameters)


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print("  Stage 12 Test Suite — Multi-Network Evidence Support")
    print("=" * 60)

    test_network_config_loading()
    test_key_normalisation()
    test_default_network()
    test_env_var_resolution()
    test_explorer_urls()
    test_list_networks()
    test_evidence_schema_network_fields()
    test_evidence_repository_migration()
    test_batch_evidence_network_fields()
    test_batch_repo_migration()
    test_proof_json_network()
    test_cli_network_flag()
    test_register_file_network_integration()
    test_backward_compatibility()

    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  Stage 12 Results: {_passed}/{total} passed, {_failed} failed")
    print(f"{'=' * 60}\n")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
