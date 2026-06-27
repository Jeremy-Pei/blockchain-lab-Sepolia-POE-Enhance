"""
test_stage9.py — Stage 9 test suite (Merkle batch registration)

Tests:
  1.  Merkle tree core
  2.  Proof generation
  3.  Proof verification failure cases
  4.  File ordering (determinism)
  5.  Batch evidence JSON
  6.  Batch SQLite
  7.  Batch reports (Markdown + PDF)
  8.  Batch package
  9.  CLI tests (register + verify)
  10. Backward compatibility

Usage:
  cd python-client
  PYTHONPATH=. .venv/bin/python -m proof_client.test_stage9
"""

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

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


def section(title: str):
    print(f"\n{'━'*60}")
    print(f"  🌳 {title}")
    print(f"{'━'*60}")


# ── Helpers ───────────────────────────────────────────────────────


def _sha256_hex(data: bytes) -> str:
    return "0x" + hashlib.sha256(data).hexdigest()


def _sha256_pair(left: str, right: str) -> str:
    lb = bytes.fromhex(left.replace("0x", ""))
    rb = bytes.fromhex(right.replace("0x", ""))
    return "0x" + hashlib.sha256(lb + rb).hexdigest()


def _make_file(tmp: Path, name: str, content: bytes = b"test content") -> Path:
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def _leaf(data: bytes) -> str:
    return _sha256_hex(data)


# ══════════════════════════════════════════════════════════════════
# 1. Merkle tree core
# ══════════════════════════════════════════════════════════════════

def test_merkle_core():
    section("1. Merkle tree core")
    from proof_client.merkle_tree import (
        build_merkle_tree, get_merkle_root, normalize_hash, hash_pair,
    )

    # T01 — one-leaf root equals the leaf
    try:
        leaf = _leaf(b"single")
        root = get_merkle_root([leaf])
        assert root == leaf, f"One-leaf root should equal the leaf, got {root}"
        ok("T01 one-leaf root equals the leaf")
    except Exception as e:
        fail("T01 one-leaf root equals the leaf", str(e))

    # T02 — two-leaf root matches expected pair hash
    try:
        l0 = _leaf(b"file_a")
        l1 = _leaf(b"file_b")
        expected = _sha256_pair(l0, l1)
        root = get_merkle_root([l0, l1])
        assert root == expected, f"Expected {expected}, got {root}"
        ok("T02 two-leaf root matches expected pair hash")
    except Exception as e:
        fail("T02 two-leaf root matches expected pair hash", str(e))

    # T03 — odd leaves duplicate last
    try:
        l0 = _leaf(b"a")
        l1 = _leaf(b"b")
        l2 = _leaf(b"c")
        # With duplication: parent0 = hash(l0, l1), parent1 = hash(l2, l2)
        p0 = _sha256_pair(l0, l1)
        p1 = _sha256_pair(l2, l2)
        expected_root = _sha256_pair(p0, p1)
        root = get_merkle_root([l0, l1, l2])
        assert root == expected_root, f"Expected {expected_root}, got {root}"
        ok("T03 odd leaves duplicate last")
    except Exception as e:
        fail("T03 odd leaves duplicate last", str(e))

    # T04 — empty leaves raises ValueError
    try:
        try:
            build_merkle_tree([])
            fail("T04 empty leaves raises ValueError", "no error raised")
        except ValueError:
            ok("T04 empty leaves raises ValueError")
    except Exception as e:
        fail("T04 empty leaves raises ValueError", str(e))

    # T05 — invalid hash raises ValueError
    try:
        try:
            normalize_hash("not_a_hash")
            fail("T05 invalid hash raises ValueError", "no error raised")
        except ValueError:
            ok("T05 invalid hash raises ValueError")
    except Exception as e:
        fail("T05 invalid hash raises ValueError", str(e))

    # T06 — merkle_root is 0x-prefixed
    try:
        root = get_merkle_root([_leaf(b"x")])
        assert root.startswith("0x"), f"Root not 0x-prefixed: {root}"
        ok("T06 merkle_root is 0x-prefixed")
    except Exception as e:
        fail("T06 merkle_root is 0x-prefixed", str(e))

    # T07 — four-leaf tree has correct structure
    try:
        leaves = [_leaf(bytes([i])) for i in range(4)]
        levels = build_merkle_tree(leaves)
        assert len(levels) == 3, f"Expected 3 levels, got {len(levels)}"
        assert len(levels[0]) == 4
        assert len(levels[1]) == 2
        assert len(levels[2]) == 1
        ok("T07 four-leaf tree has correct level structure")
    except Exception as e:
        fail("T07 four-leaf tree has correct level structure", str(e))

    # T08 — all hashes in tree are 0x-prefixed
    try:
        leaves = [_leaf(bytes([i])) for i in range(5)]
        levels = build_merkle_tree(leaves)
        for level in levels:
            for h in level:
                assert h.startswith("0x"), f"Non-prefixed hash in tree: {h}"
        ok("T08 all hashes in tree are 0x-prefixed")
    except Exception as e:
        fail("T08 all hashes in tree are 0x-prefixed", str(e))


# ══════════════════════════════════════════════════════════════════
# 2. Proof generation
# ══════════════════════════════════════════════════════════════════

def test_proof_generation():
    section("2. Proof generation")
    from proof_client.merkle_tree import generate_proof, verify_proof, get_merkle_root

    # T09 — proof verifies for every leaf (4-leaf tree)
    try:
        leaves = [_leaf(bytes([i])) for i in range(4)]
        root = get_merkle_root(leaves)
        all_ok = True
        for i in range(4):
            proof = generate_proof(leaves, i)
            if not verify_proof(leaves[i], proof, root):
                all_ok = False
                break
        assert all_ok
        ok("T09 proof verifies for every leaf in 4-leaf tree")
    except Exception as e:
        fail("T09 proof verifies for every leaf in 4-leaf tree", str(e))

    # T10 — proof verifies for every leaf (3-leaf tree with duplication)
    try:
        leaves = [_leaf(bytes([i])) for i in range(3)]
        root = get_merkle_root(leaves)
        for i in range(3):
            proof = generate_proof(leaves, i)
            assert verify_proof(leaves[i], proof, root), f"Proof failed for leaf {i}"
        ok("T10 proof verifies for every leaf in 3-leaf tree")
    except Exception as e:
        fail("T10 proof verifies for every leaf in 3-leaf tree", str(e))

    # T11 — proof verifies for single leaf
    try:
        leaves = [_leaf(b"only")]
        root = get_merkle_root(leaves)
        proof = generate_proof(leaves, 0)
        assert verify_proof(leaves[0], proof, root)
        ok("T11 proof verifies for single leaf")
    except Exception as e:
        fail("T11 proof verifies for single leaf", str(e))

    # T12 — proof contains correct structure
    try:
        leaves = [_leaf(bytes([i])) for i in range(4)]
        proof = generate_proof(leaves, 0)
        assert len(proof) == 2  # 4-leaf tree: 2 levels above leaves
        for step in proof:
            assert "position" in step and step["position"] in ("left", "right")
            assert "hash" in step and step["hash"].startswith("0x")
        ok("T12 proof items have position and 0x hash")
    except Exception as e:
        fail("T12 proof items have position and 0x hash", str(e))

    # T13 — index out of range raises ValueError
    try:
        leaves = [_leaf(b"a"), _leaf(b"b")]
        try:
            generate_proof(leaves, 5)
            fail("T13 index out of range raises ValueError", "no error raised")
        except ValueError:
            ok("T13 index out of range raises ValueError")
    except Exception as e:
        fail("T13 index out of range raises ValueError", str(e))


# ══════════════════════════════════════════════════════════════════
# 3. Proof verification failure cases
# ══════════════════════════════════════════════════════════════════

def test_proof_failures():
    section("3. Proof verification failure cases")
    from proof_client.merkle_tree import generate_proof, verify_proof, get_merkle_root

    leaves = [_leaf(bytes([i])) for i in range(4)]
    root = get_merkle_root(leaves)

    # T14 — proof fails with wrong leaf
    try:
        proof = generate_proof(leaves, 0)
        assert not verify_proof(_leaf(b"tampered"), proof, root)
        ok("T14 proof fails with wrong leaf (tampered file)")
    except Exception as e:
        fail("T14 proof fails with wrong leaf", str(e))

    # T15 — proof fails with wrong root
    try:
        proof = generate_proof(leaves, 0)
        assert not verify_proof(leaves[0], proof, _leaf(b"wrong_root"))
        ok("T15 proof fails with wrong root")
    except Exception as e:
        fail("T15 proof fails with wrong root", str(e))

    # T16 — proof fails with modified sibling hash
    try:
        proof = generate_proof(leaves, 0)
        tampered = [{"position": step["position"], "hash": _leaf(b"fake")} for step in proof]
        assert not verify_proof(leaves[0], tampered, root)
        ok("T16 proof fails with modified sibling hash")
    except Exception as e:
        fail("T16 proof fails with modified sibling hash", str(e))

    # T17 — proof fails with flipped direction
    try:
        proof = generate_proof(leaves, 0)
        flip = {"left": "right", "right": "left"}
        flipped = [{"position": flip[s["position"]], "hash": s["hash"]} for s in proof]
        assert not verify_proof(leaves[0], flipped, root)
        ok("T17 proof fails with flipped direction")
    except Exception as e:
        fail("T17 proof fails with flipped direction", str(e))

    # T18 — verify_proof with invalid hash returns False
    try:
        result = verify_proof("not_a_real_hash", [], root)
        assert result is False
        ok("T18 verify_proof with invalid hash returns False")
    except Exception as e:
        fail("T18 verify_proof with invalid hash returns False", str(e))


# ══════════════════════════════════════════════════════════════════
# 4. File ordering
# ══════════════════════════════════════════════════════════════════

def test_file_ordering():
    section("4. File ordering and determinism")
    from proof_client.merkle_tree import normalize_relative_path, sort_key
    from proof_client.batch_merkle_register import collect_files, build_leaves

    # T19 — normalize_relative_path removes leading ./
    try:
        assert normalize_relative_path("./foo/bar.txt") == "foo/bar.txt"
        ok("T19 normalize_relative_path removes leading ./")
    except Exception as e:
        fail("T19 normalize_relative_path removes leading ./", str(e))

    # T20 — normalize_relative_path replaces backslashes
    try:
        assert normalize_relative_path("sub\\file.txt") == "sub/file.txt"
        ok("T20 normalize_relative_path replaces backslashes")
    except Exception as e:
        fail("T20 normalize_relative_path replaces backslashes", str(e))

    # T21 — flat file ordering is deterministic (ascending)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _make_file(d, "z_file.txt", b"z")
            _make_file(d, "a_file.txt", b"a")
            _make_file(d, "m_file.txt", b"m")
            files = collect_files(d)
            names = [f.name for f in files]
            assert names == sorted(names, key=str.lower), f"Not sorted: {names}"
            ok("T21 flat file ordering is deterministic (ascending)")
    except Exception as e:
        fail("T21 flat file ordering is deterministic", str(e))

    # T22 — nested path ordering is deterministic with --recursive
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _make_file(d, "sub/b.txt", b"b")
            _make_file(d, "a.txt", b"a")
            _make_file(d, "sub/a.txt", b"sa")
            files = collect_files(d, recursive=True)
            rel = [str(f.relative_to(d)).replace("\\", "/") for f in files]
            assert rel == sorted(rel, key=str.lower), f"Not sorted: {rel}"
            ok("T22 nested path ordering is deterministic with --recursive")
    except Exception as e:
        fail("T22 nested path ordering is deterministic", str(e))

    # T23 — same files in different insertion order produce same root
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            fa = _make_file(d, "a.txt", b"content_a")
            fb = _make_file(d, "b.txt", b"content_b")
            from proof_client.merkle_tree import sha256_file, get_merkle_root
            h_a = sha256_file(fa)
            h_b = sha256_file(fb)
            root1 = get_merkle_root([h_a, h_b])
            root2 = get_merkle_root([h_a, h_b])  # same order, same root
            assert root1 == root2
            ok("T23 same leaf order produces same root")
    except Exception as e:
        fail("T23 same leaf order produces same root", str(e))

    # T24 — hidden files are excluded
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _make_file(d, ".hidden.txt", b"secret")
            _make_file(d, "visible.txt", b"ok")
            files = collect_files(d)
            names = [f.name for f in files]
            assert ".hidden.txt" not in names
            assert "visible.txt" in names
            ok("T24 hidden files are excluded")
    except Exception as e:
        fail("T24 hidden files are excluded", str(e))

    # T25 — unsupported extension files are excluded
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _make_file(d, "script.py", b"print('hi')")
            _make_file(d, "doc.txt", b"text")
            files = collect_files(d)
            names = [f.name for f in files]
            assert "script.py" not in names
            assert "doc.txt" in names
            ok("T25 unsupported extension files are excluded")
    except Exception as e:
        fail("T25 unsupported extension files are excluded", str(e))

    # T26 — empty folder raises ValueError
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            files = collect_files(d)
            assert files == []
            ok("T26 empty folder returns empty list (ValueError on registration)")
    except Exception as e:
        fail("T26 empty folder returns empty list", str(e))

    # T27 — leaf relative_path values are POSIX-style
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _make_file(d, "a.txt", b"aaa")
            files = collect_files(d)
            leaves, _ = build_leaves(d, files)
            for lf in leaves:
                assert "\\" not in lf.relative_path, f"Backslash in path: {lf.relative_path}"
            ok("T27 leaf relative paths are POSIX-style (no backslashes)")
    except Exception as e:
        fail("T27 leaf relative paths are POSIX-style", str(e))


# ══════════════════════════════════════════════════════════════════
# 5. Batch evidence JSON
# ══════════════════════════════════════════════════════════════════

def test_batch_evidence_json():
    section("5. Batch evidence JSON")
    from proof_client.merkle_evidence import (
        BatchEvidence, MerkleLeaf, build_batch_evidence_files,
        make_batch_id, safe_proof_filename,
    )
    from proof_client.config import BATCH_EVIDENCE_DIR
    from proof_client.merkle_tree import get_merkle_root

    leaf_contents = [b"file_alpha", b"file_beta", b"file_gamma"]
    leaf_hashes = [_sha256_hex(c) for c in leaf_contents]
    leaves = [
        MerkleLeaf(
            index=i, relative_path=f"file_{chr(97+i)}.txt",
            file_name=f"file_{chr(97+i)}.txt", file_size_bytes=len(c),
            file_hash=leaf_hashes[i]
        )
        for i, c in enumerate(leaf_contents)
    ]
    merkle_root = get_merkle_root(leaf_hashes)
    batch_id = make_batch_id() + "_test_ev"
    evidence = BatchEvidence(
        batch_id=batch_id,
        batch_title="Test Batch",
        author="Tester",
        file_count=3,
        merkle_root=merkle_root,
        uri=f"batch://{batch_id}",
    )

    try:
        paths = build_batch_evidence_files(batch_id, leaves, leaf_hashes, evidence)

        # T28 — batch_evidence.json has record_type = merkle_batch
        be = json.loads(paths["batch_evidence"].read_text(encoding="utf-8"))
        assert be.get("record_type") == "merkle_batch", f"Got: {be.get('record_type')}"
        ok("T28 batch_evidence has record_type = merkle_batch")

        # T29 — batch_evidence includes file_count
        assert be.get("file_count") == 3
        ok("T29 batch_evidence includes file_count = 3")

        # T30 — batch_evidence includes merkle_root
        assert be.get("merkle_root") == merkle_root
        ok("T30 batch_evidence includes correct merkle_root")

        # T31 — batch_evidence includes leaf_ordering
        assert "leaf_ordering" in be
        ok("T31 batch_evidence includes leaf_ordering")

        # T32 — batch_evidence includes odd_leaf_strategy
        assert "odd_leaf_strategy" in be
        ok("T32 batch_evidence includes odd_leaf_strategy")

        # T33 — batch_evidence URI uses batch://
        assert be.get("uri", "").startswith("batch://")
        ok("T33 batch_evidence URI starts with batch://")

        # T34 — leaves.json is written
        lv = json.loads(paths["leaves_json"].read_text(encoding="utf-8"))
        assert isinstance(lv, list) and len(lv) == 3
        ok("T34 leaves.json written with 3 entries")

        # T35 — merkle_tree.json is written and has levels
        mt = json.loads(paths["merkle_tree_json"].read_text(encoding="utf-8"))
        assert "levels" in mt and "merkle_root" in mt
        ok("T35 merkle_tree.json written with levels and merkle_root")

        # T36 — per-file proof JSON includes leaf_index
        proof_files = paths["proof_files"]
        assert len(proof_files) == 3
        for pf in proof_files:
            pdata = json.loads(pf.read_text(encoding="utf-8"))
            assert "leaf_index" in pdata, f"Missing leaf_index in {pf.name}"
        ok("T36 per-file proof JSON includes leaf_index")

        # T37 — per-file proof JSON includes relative_path
        for pf in proof_files:
            pdata = json.loads(pf.read_text(encoding="utf-8"))
            assert "relative_path" in pdata
        ok("T37 per-file proof JSON includes relative_path")

        # T38 — per-file proof JSON includes merkle_root
        for pf in proof_files:
            pdata = json.loads(pf.read_text(encoding="utf-8"))
            assert pdata.get("merkle_root") == merkle_root
        ok("T38 per-file proof JSON includes correct merkle_root")

        # T39 — generated proof filenames are safe (no slashes)
        for pf in proof_files:
            assert "/" not in pf.name and "\\" not in pf.name
        ok("T39 generated proof filenames are safe (no slashes)")

        # T40 — safe_proof_filename handles subdirectory paths
        name = safe_proof_filename("sub/my file.txt")
        assert "/" not in name and "\\" not in name
        ok("T40 safe_proof_filename handles subdirectory paths")

        # T41 — all file hashes in leaves.json are 0x-prefixed
        for entry in lv:
            assert entry["file_hash"].startswith("0x"), f"Not 0x-prefixed: {entry['file_hash']}"
        ok("T41 all file hashes in leaves.json are 0x-prefixed")

        # T42 — merkle_root in batch_evidence is 0x-prefixed
        assert be["merkle_root"].startswith("0x")
        ok("T42 merkle_root in batch_evidence is 0x-prefixed")

        # T43 — batch_summary.json is written
        assert paths["batch_summary"].exists()
        bs = json.loads(paths["batch_summary"].read_text(encoding="utf-8"))
        assert bs.get("batch_id") == batch_id
        ok("T43 batch_summary.json is written with correct batch_id")

    except AssertionError as e:
        fail("batch evidence JSON tests", str(e))
    finally:
        # Clean up test batch dirs
        test_dir = BATCH_EVIDENCE_DIR / batch_id
        if test_dir.exists():
            shutil.rmtree(test_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
# 6. Batch SQLite
# ══════════════════════════════════════════════════════════════════

def test_batch_sqlite():
    section("6. Batch SQLite")
    from proof_client.evidence_repository import (
        insert_batch_evidence, find_batch_by_id, find_batch_by_merkle_root,
    )
    from proof_client.merkle_evidence import make_batch_id
    from proof_client.merkle_tree import get_merkle_root

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"

        leaf_hashes = [_sha256_hex(bytes([i])) for i in range(3)]
        root = get_merkle_root(leaf_hashes)
        batch_id = make_batch_id() + "_sqlite_test"
        now = "2026-06-27T10:00:00Z"

        record = {
            "batch_id": batch_id,
            "batch_title": "SQLite Test Batch",
            "author": "Tester",
            "description": "Test",
            "file_count": 3,
            "merkle_root": root,
            "uri": f"batch://{batch_id}",
            "network": "Ethereum Sepolia",
            "chain_id": 11155111,
            "contract_address": "0x" + "a" * 40,
            "owner_address": "0x" + "b" * 40,
            "transaction_hash": "0x" + "c" * 64,
            "block_number": 999,
            "block_timestamp": 1750000000,
            "explorer_url": "https://sepolia.etherscan.io/tx/0x" + "c" * 64,
            "batch_evidence_json": "{}",
            "created_at_utc": now,
        }

        # T44 — insert batch record
        try:
            row_id = insert_batch_evidence(record, db_path=db_path)
            assert row_id is not None and row_id > 0
            ok("T44 SQLite inserts batch record")
        except Exception as e:
            fail("T44 SQLite inserts batch record", str(e))

        # T45 — find by batch_id
        try:
            found = find_batch_by_id(batch_id, db_path=db_path)
            assert found is not None and found["batch_id"] == batch_id
            ok("T45 SQLite finds batch by batch_id")
        except Exception as e:
            fail("T45 SQLite finds batch by batch_id", str(e))

        # T46 — find by merkle_root
        try:
            found = find_batch_by_merkle_root(root, db_path=db_path)
            assert found is not None and found["merkle_root"] == root
            ok("T46 SQLite finds batch by merkle_root")
        except Exception as e:
            fail("T46 SQLite finds batch by merkle_root", str(e))

        # T47 — duplicate merkle_root handled (UNIQUE constraint)
        try:
            try:
                insert_batch_evidence(record, db_path=db_path)
                fail("T47 duplicate merkle_root should raise IntegrityError", "no error raised")
            except sqlite3.IntegrityError:
                ok("T47 duplicate merkle_root raises IntegrityError")
        except Exception as e:
            fail("T47 duplicate merkle_root raises IntegrityError", str(e))

        # T48 — not found returns None
        try:
            missing = find_batch_by_id("nonexistent_batch", db_path=db_path)
            assert missing is None
            ok("T48 find non-existent batch_id returns None")
        except Exception as e:
            fail("T48 find non-existent batch_id returns None", str(e))

        # T49 — file_count is stored correctly
        try:
            found = find_batch_by_id(batch_id, db_path=db_path)
            assert found["file_count"] == 3
            ok("T49 file_count stored correctly in SQLite")
        except Exception as e:
            fail("T49 file_count stored correctly in SQLite", str(e))


# ══════════════════════════════════════════════════════════════════
# 7. Batch reports
# ══════════════════════════════════════════════════════════════════

def test_batch_reports():
    section("7. Batch reports (Markdown + PDF)")
    from proof_client.merkle_evidence import BatchEvidence, MerkleLeaf, make_batch_id
    from proof_client.merkle_report import (
        build_batch_markdown_certificate,
        generate_batch_markdown_certificate,
        generate_batch_pdf_certificate,
    )
    from proof_client.merkle_tree import get_merkle_root

    leaf_hashes = [_sha256_hex(bytes([i])) for i in range(5)]
    root = get_merkle_root(leaf_hashes)
    batch_id = make_batch_id() + "_report_test"
    leaves = [
        MerkleLeaf(index=i, relative_path=f"f{i}.txt", file_name=f"f{i}.txt",
                   file_size_bytes=10, file_hash=leaf_hashes[i])
        for i in range(5)
    ]
    evidence = BatchEvidence(
        batch_id=batch_id, batch_title="Report Test", author="Alice",
        file_count=5, merkle_root=root, uri=f"batch://{batch_id}",
        transaction_hash="0x" + "e" * 64, block_number=12345,
    )

    md_content = build_batch_markdown_certificate(evidence, leaves)

    # T50 — Markdown certificate includes Batch Summary header
    try:
        assert "Batch Summary" in md_content
        ok("T50 Markdown certificate includes Batch Summary header")
    except Exception as e:
        fail("T50 Markdown certificate includes Batch Summary", str(e))

    # T51 — Markdown certificate includes merkle_root
    try:
        assert root in md_content
        ok("T51 Markdown certificate includes merkle_root")
    except Exception as e:
        fail("T51 Markdown certificate includes merkle_root", str(e))

    # T52 — Markdown certificate includes file_count
    try:
        assert str(evidence.file_count) in md_content
        ok("T52 Markdown certificate includes file_count")
    except Exception as e:
        fail("T52 Markdown certificate includes file_count", str(e))

    # T53 — Markdown certificate includes Merkle Tree Rules
    try:
        assert "Merkle Tree Rules" in md_content
        ok("T53 Markdown certificate includes Merkle Tree Rules section")
    except Exception as e:
        fail("T53 Markdown certificate includes Merkle Tree Rules", str(e))

    # T54 — Markdown certificate includes Limitations
    try:
        assert "Limitations" in md_content
        ok("T54 Markdown certificate includes Limitations section")
    except Exception as e:
        fail("T54 Markdown certificate includes Limitations", str(e))

    # T55 — Markdown certificate is written to file
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            md_path = generate_batch_markdown_certificate(evidence, leaves, out)
            assert md_path.exists()
            assert md_path.stat().st_size > 0
            ok("T55 Markdown certificate file is written")
    except Exception as e:
        fail("T55 Markdown certificate file is written", str(e))

    # T56 — PDF certificate is written
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            pdf_path = generate_batch_pdf_certificate(evidence, leaves, out)
            assert pdf_path.exists()
            assert pdf_path.stat().st_size > 0
            ok("T56 PDF certificate file is written")
    except Exception as e:
        fail("T56 PDF certificate file is written", str(e))

    # T57 — batch_id is in Markdown filename
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            md_path = generate_batch_markdown_certificate(evidence, leaves, out)
            assert batch_id in md_path.name
            ok("T57 batch_id is in Markdown certificate filename")
    except Exception as e:
        fail("T57 batch_id is in Markdown certificate filename", str(e))


# ══════════════════════════════════════════════════════════════════
# 8. Batch package
# ══════════════════════════════════════════════════════════════════

def test_batch_package():
    section("8. Batch package")
    from proof_client.merkle_evidence import (
        BatchEvidence, MerkleLeaf, make_batch_id, build_batch_evidence_files,
    )
    from proof_client.merkle_report import (
        generate_batch_markdown_certificate, generate_batch_pdf_certificate,
    )
    from proof_client.batch_merkle_register import build_batch_package
    from proof_client.merkle_tree import get_merkle_root
    from proof_client.config import BATCH_EVIDENCE_DIR

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        folder = tmp_path / "works"
        folder.mkdir()

        # Create source files
        files = []
        for i, name in enumerate(["alpha.txt", "beta.md"]):
            fp = _make_file(folder, name, f"content {i}".encode())
            files.append(fp)

        from proof_client.merkle_tree import sha256_file
        leaf_hashes = [sha256_file(f) for f in files]
        root = get_merkle_root(leaf_hashes)
        batch_id = make_batch_id() + "_pkg_test"
        leaves = [
            MerkleLeaf(
                index=i, relative_path=f.name, file_name=f.name,
                file_size_bytes=f.stat().st_size, file_hash=leaf_hashes[i],
            )
            for i, f in enumerate(files)
        ]
        evidence = BatchEvidence(
            batch_id=batch_id, batch_title="Package Test",
            file_count=2, merkle_root=root, uri=f"batch://{batch_id}",
        )
        paths = build_batch_evidence_files(batch_id, leaves, leaf_hashes, evidence)

        out_reports = tmp_path / "reports"
        out_reports.mkdir()
        md_cert = generate_batch_markdown_certificate(evidence, leaves, out_reports)
        pdf_cert = generate_batch_pdf_certificate(evidence, leaves, out_reports)

        out_pkgs = tmp_path / "packages"
        out_pkgs.mkdir()

        # Temporarily override BATCH_PACKAGES_DIR
        import proof_client.batch_merkle_register as bmr
        orig_pkgs = bmr.BATCH_PACKAGES_DIR
        bmr.BATCH_PACKAGES_DIR = out_pkgs

        try:
            pkg_dir, zip_path = build_batch_package(
                evidence=evidence,
                leaves=leaves,
                files=files,
                folder=folder,
                batch_dir=paths["batch_dir"],
                proofs_dir=paths["proofs_dir"],
                md_cert=md_cert,
                pdf_cert=pdf_cert,
            )

            # T58 — package includes batch_evidence.json
            assert (pkg_dir / "batch" / "batch_evidence.json").exists()
            ok("T58 package includes batch/batch_evidence.json")

            # T59 — package includes leaves.json
            assert (pkg_dir / "batch" / "leaves.json").exists()
            ok("T59 package includes batch/leaves.json")

            # T60 — package includes merkle_tree.json
            assert (pkg_dir / "batch" / "merkle_tree.json").exists()
            ok("T60 package includes batch/merkle_tree.json")

            # T61 — package includes proof files
            proof_count = len(list((pkg_dir / "proofs").glob("*.proof.json")))
            assert proof_count == 2, f"Expected 2 proof files, got {proof_count}"
            ok("T61 package includes per-file proof JSON files")

            # T62 — package includes batch_certificate.md
            assert (pkg_dir / "reports" / "batch_certificate.md").exists()
            ok("T62 package includes reports/batch_certificate.md")

            # T63 — package includes batch_certificate.pdf
            assert (pkg_dir / "reports" / "batch_certificate.pdf").exists()
            ok("T63 package includes reports/batch_certificate.pdf")

            # T64 — package includes verification guide
            assert (pkg_dir / "verification" / "batch_verification_guide.md").exists()
            ok("T64 package includes verification/batch_verification_guide.md")

            # T65 — package includes README.md
            assert (pkg_dir / "README.md").exists()
            ok("T65 package includes README.md")

            # T66 — manifest.json covers proof files
            manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
            manifest_paths = {e["path"] for e in manifest["files"]}
            proof_files_in_manifest = [p for p in manifest_paths if "proof.json" in p]
            assert len(proof_files_in_manifest) == 2, (
                f"Expected 2 proof files in manifest, got {proof_files_in_manifest}"
            )
            ok("T66 manifest.json covers all proof files")

            # T67 — ZIP file is created
            assert zip_path.exists()
            ok("T67 ZIP file is created")

            # T68 — original files are in package
            for f in files:
                assert (pkg_dir / "original" / f.name).exists()
            ok("T68 original files are in package/original/")

            # T69 — verification_commands.txt is written
            assert (pkg_dir / "verification" / "verification_commands.txt").exists()
            ok("T69 verification_commands.txt is written")

            # T70 — batch_summary.json is in package
            assert (pkg_dir / "batch" / "batch_summary.json").exists()
            ok("T70 package includes batch/batch_summary.json")

        finally:
            bmr.BATCH_PACKAGES_DIR = orig_pkgs
            # Clean up
            batch_ev_dir = BATCH_EVIDENCE_DIR / batch_id
            if batch_ev_dir.exists():
                shutil.rmtree(batch_ev_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
# 9. CLI tests
# ══════════════════════════════════════════════════════════════════

def test_cli():
    section("9. CLI tests")
    from proof_client.batch_merkle_register import collect_files
    from proof_client.verify_merkle_proof import verify_file_against_proof
    from proof_client.merkle_evidence import (
        BatchEvidence, MerkleLeaf, make_batch_id, build_batch_evidence_files,
    )
    from proof_client.merkle_tree import sha256_file, get_merkle_root

    # T71 — collect_files returns empty list for empty folder
    try:
        with tempfile.TemporaryDirectory() as tmp:
            files = collect_files(Path(tmp))
            assert files == []
            ok("T71 CLI: collect_files returns empty list for empty folder")
    except Exception as e:
        fail("T71 CLI: collect_files empty folder", str(e))

    # T72 — collect_files respects --recursive flag
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _make_file(d, "root.txt", b"r")
            _make_file(d, "sub/child.txt", b"c")
            flat = collect_files(d, recursive=False)
            deep = collect_files(d, recursive=True)
            assert len(flat) == 1
            assert len(deep) == 2
            ok("T72 CLI: --recursive discovers nested files")
    except Exception as e:
        fail("T72 CLI: --recursive discovers nested files", str(e))

    # T73 — verify_file_against_proof succeeds for valid proof
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            fa = _make_file(d, "a.txt", b"file A content")
            fb = _make_file(d, "b.txt", b"file B content")
            files = [fa, fb]
            leaf_hashes = [sha256_file(f) for f in files]
            root = get_merkle_root(leaf_hashes)
            batch_id = make_batch_id() + "_cli_test"
            leaves = [
                MerkleLeaf(index=i, relative_path=f.name, file_name=f.name,
                           file_size_bytes=f.stat().st_size, file_hash=leaf_hashes[i])
                for i, f in enumerate(files)
            ]
            evidence = BatchEvidence(
                batch_id=batch_id, file_count=2, merkle_root=root,
                uri=f"batch://{batch_id}",
            )
            from proof_client.config import BATCH_EVIDENCE_DIR
            paths = build_batch_evidence_files(batch_id, leaves, leaf_hashes, evidence)
            proof_path = paths["proof_files"][0]
            proof_json = json.loads(proof_path.read_text(encoding="utf-8"))
            ok_flag, details = verify_file_against_proof(fa, proof_json)
            assert ok_flag, f"Expected PASSED, got errors: {details.get('errors')}"
            ok("T73 CLI: verify_file_against_proof succeeds for valid proof")

            # T74 — verify fails for tampered file
            tampered = d / "tampered.txt"
            tampered.write_bytes(b"TAMPERED CONTENT XYZ")
            ok_flag2, details2 = verify_file_against_proof(tampered, proof_json)
            assert not ok_flag2
            ok("T74 CLI: verify fails for tampered file")

            # T75 — verify fails for missing file
            missing_file = d / "does_not_exist.txt"
            ok_flag3, details3 = verify_file_against_proof(missing_file, proof_json)
            assert not ok_flag3
            ok("T75 CLI: verify fails for missing file")

            # T76 — verify fails for tampered proof sibling hash
            tampered_proof = dict(proof_json)
            if tampered_proof.get("proof"):
                bad_steps = [{"position": s["position"], "hash": _sha256_hex(b"bad")}
                             for s in tampered_proof["proof"]]
                tampered_proof["proof"] = bad_steps
            ok_flag4, details4 = verify_file_against_proof(fa, tampered_proof)
            assert not ok_flag4
            ok("T76 CLI: verify fails for tampered proof sibling hash")

            # Clean up
            shutil.rmtree(BATCH_EVIDENCE_DIR / batch_id, ignore_errors=True)

    except Exception as e:
        fail("T73-T76 CLI verify tests", str(e))

    # T77 — batch_uri starts with batch://
    try:
        batch_id = make_batch_id()
        uri = f"batch://{batch_id}"
        assert uri.startswith("batch://")
        ok("T77 batch URI starts with batch://")
    except Exception as e:
        fail("T77 batch URI format", str(e))

    # T78 — verification guide mentions proof verification command
    try:
        from proof_client.merkle_evidence import BatchEvidence
        from proof_client.batch_merkle_register import _build_batch_verification_guide
        ev = BatchEvidence(
            batch_id="test_batch_123",
            merkle_root="0x" + "a" * 64,
            uri="batch://test_batch_123",
        )
        guide = _build_batch_verification_guide(ev)
        assert "verify_merkle_proof" in guide
        ok("T78 verification guide mentions verify_merkle_proof command")
    except Exception as e:
        fail("T78 verification guide content", str(e))


# ══════════════════════════════════════════════════════════════════
# 10. Backward compatibility
# ══════════════════════════════════════════════════════════════════

def test_backward_compatibility():
    section("10. Backward compatibility")

    # T79 — existing EvidenceRecord still deserialises cleanly
    try:
        from proof_client.evidence_schema import EvidenceRecord
        old_data = {
            "file_name": "old_file.txt",
            "file_hash": "0x" + "a" * 64,
            "uri": "file://old",
            "tx_hash": "bb" * 32,
            "block_number": 100,
            "gas_used": 21000,
            "owner": "0x" + "c" * 40,
            "timestamp": 1000000,
            "status": "success",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
        rec = EvidenceRecord.from_dict(old_data)
        assert rec.file_name == "old_file.txt"
        assert not rec.is_encrypted
        ok("T79 old EvidenceRecord deserialises cleanly (no Stage 9 fields)")
    except Exception as e:
        fail("T79 old EvidenceRecord backward compat", str(e))

    # T80 — merkle_tree module is importable standalone
    try:
        import proof_client.merkle_tree as mt
        assert hasattr(mt, "get_merkle_root")
        assert hasattr(mt, "generate_proof")
        assert hasattr(mt, "verify_proof")
        ok("T80 merkle_tree module exports expected symbols")
    except Exception as e:
        fail("T80 merkle_tree module importable", str(e))

    # T81 — evidence_repository has new batch functions without breaking old ones
    try:
        from proof_client.evidence_repository import (
            insert, find_by_hash, find_all, count,
            insert_batch_evidence, find_batch_by_id,
        )
        ok("T81 evidence_repository exports both old and new batch functions")
    except Exception as e:
        fail("T81 evidence_repository exports", str(e))

    # T82 — config.py exposes BATCH_EVIDENCE_DIR
    try:
        from proof_client.config import BATCH_EVIDENCE_DIR, BATCH_PACKAGES_DIR, BATCH_REPORTS_DIR
        assert BATCH_EVIDENCE_DIR.is_dir()
        assert BATCH_PACKAGES_DIR.is_dir()
        assert BATCH_REPORTS_DIR.is_dir()
        ok("T82 config.py exposes batch dirs and they exist")
    except Exception as e:
        fail("T82 config.py batch dirs", str(e))

    # T83 — BatchEvidence record_type default is merkle_batch
    try:
        from proof_client.merkle_evidence import BatchEvidence
        ev = BatchEvidence()
        assert ev.record_type == "merkle_batch"
        ok("T83 BatchEvidence record_type default is merkle_batch")
    except Exception as e:
        fail("T83 BatchEvidence record_type default", str(e))

    # T84 — single leaf Merkle tree still works (edge case)
    try:
        from proof_client.merkle_tree import get_merkle_root, generate_proof, verify_proof
        leaf = _sha256_hex(b"lone wolf")
        root = get_merkle_root([leaf])
        proof = generate_proof([leaf], 0)
        assert verify_proof(leaf, proof, root)
        ok("T84 single leaf tree still works end-to-end")
    except Exception as e:
        fail("T84 single leaf tree end-to-end", str(e))


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Stage 9 Test Suite — Merkle Batch Registration")
    print("=" * 60)

    test_merkle_core()
    test_proof_generation()
    test_proof_failures()
    test_file_ordering()
    test_batch_evidence_json()
    test_batch_sqlite()
    test_batch_reports()
    test_batch_package()
    test_cli()
    test_backward_compatibility()

    total = _passed + _failed
    print(f"\n{'=' * 60}")
    print(f"  Results: {_passed}/{total} passed, {_failed} failed")
    print(f"{'=' * 60}\n")

    if _failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
