"""
merkle_tree.py — Deterministic Merkle tree construction and proof verification

Rules (must be followed exactly for third-party reproducibility):
  Leaf hash:       SHA-256(file bytes)
  Leaf ordering:   normalized relative path, ascending lexicographic order
  Internal node:   SHA-256(left_child_bytes || right_child_bytes)
  Odd-level pad:   duplicate the last node
  Hash encoding:   0x-prefixed lowercase hex string

These rules are documented in batch_evidence.json so any verifier can
independently reconstruct the tree and confirm the root.
"""

import hashlib
from pathlib import Path


# ── Low-level hash helpers ─────────────────────────────────────────


def normalize_hash(hex_hash: str) -> str:
    """Return a 0x-prefixed, lowercase, 64-char hex hash string."""
    s = hex_hash.lower()
    if s.startswith("0x"):
        h = s[2:]
    else:
        h = s
    if len(h) != 64:
        raise ValueError(f"Expected 64-character hex hash, got {len(h)}: {hex_hash!r}")
    return "0x" + h


def hash_pair(left_hash: str, right_hash: str) -> str:
    """SHA-256(left_bytes || right_bytes) → 0x-prefixed hex string."""
    left_bytes = bytes.fromhex(left_hash.replace("0x", ""))
    right_bytes = bytes.fromhex(right_hash.replace("0x", ""))
    digest = hashlib.sha256(left_bytes + right_bytes).hexdigest()
    return "0x" + digest


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file and return 0x-prefixed hex string."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "0x" + h.hexdigest()


def sha256_bytes_hex(data: bytes) -> str:
    """SHA-256 of raw bytes → 0x-prefixed hex string."""
    return "0x" + hashlib.sha256(data).hexdigest()


# ── Merkle tree construction ───────────────────────────────────────


def build_merkle_tree(leaves: list[str]) -> list[list[str]]:
    """
    Build a full Merkle tree from a list of leaf hashes.

    Args:
        leaves: List of 0x-prefixed hex leaf hashes, in sorted order.

    Returns:
        List of levels, index 0 = leaf level, last = [root].
        Each level is a list of 0x-prefixed hex strings.

    Raises:
        ValueError: If leaves is empty or contains an invalid hash.
    """
    if not leaves:
        raise ValueError("Cannot build a Merkle tree from an empty list of leaves.")

    # Normalise and validate every leaf.
    current_level = [normalize_hash(h) for h in leaves]
    levels = [list(current_level)]

    while len(current_level) > 1:
        # Pad to even length by duplicating the last element.
        if len(current_level) % 2 == 1:
            current_level = current_level + [current_level[-1]]

        next_level = []
        for i in range(0, len(current_level), 2):
            next_level.append(hash_pair(current_level[i], current_level[i + 1]))
        current_level = next_level
        levels.append(list(current_level))

    return levels


def get_merkle_root(leaves: list[str]) -> str:
    """Return the Merkle root for the given leaf hashes."""
    levels = build_merkle_tree(leaves)
    return levels[-1][0]


# ── Proof generation and verification ─────────────────────────────


def generate_proof(leaves: list[str], index: int) -> list[dict]:
    """
    Generate a Merkle proof for the leaf at *index*.

    Each proof item:
        {
            "position": "left" | "right",
            "hash": "0x..."
        }

    "position" describes the sibling's position relative to the current node:
      - "right": sibling is to the right  → compute hash_pair(current, sibling)
      - "left":  sibling is to the left   → compute hash_pair(sibling, current)

    Args:
        leaves: Full list of leaf hashes (sorted order).
        index: Zero-based index of the target leaf.

    Returns:
        List of proof steps from leaf level up to (but not including) root.

    Raises:
        ValueError: If leaves is empty or index is out of range.
    """
    if not leaves:
        raise ValueError("Cannot generate a proof from an empty leaf list.")
    if not (0 <= index < len(leaves)):
        raise ValueError(f"Index {index} out of range for {len(leaves)} leaves.")

    # Build tree with padded levels so sibling indices are consistent.
    proof: list[dict] = []
    current_level = [normalize_hash(h) for h in leaves]
    current_index = index

    while len(current_level) > 1:
        # Pad to even length.
        padded = current_level[:]
        if len(padded) % 2 == 1:
            padded.append(padded[-1])

        # Determine sibling.
        if current_index % 2 == 0:
            # Current node is left; sibling is to the right.
            sibling_index = current_index + 1
            proof.append({"position": "right", "hash": padded[sibling_index]})
        else:
            # Current node is right; sibling is to the left.
            sibling_index = current_index - 1
            proof.append({"position": "left", "hash": padded[sibling_index]})

        # Ascend one level.
        next_level = []
        for i in range(0, len(padded), 2):
            next_level.append(hash_pair(padded[i], padded[i + 1]))
        current_level = next_level
        current_index //= 2

    return proof


def verify_proof(leaf_hash: str, proof: list[dict], root: str) -> bool:
    """
    Verify a Merkle proof.

    Args:
        leaf_hash: 0x-prefixed SHA-256 hash of the target file.
        proof: List of proof steps (position + sibling hash).
        root: Expected Merkle root (0x-prefixed hex).

    Returns:
        True if the proof is valid and reproduces the expected root.
    """
    try:
        current = normalize_hash(leaf_hash)
        for step in proof:
            sibling = normalize_hash(step["hash"])
            pos = step["position"]
            if pos == "right":
                current = hash_pair(current, sibling)
            elif pos == "left":
                current = hash_pair(sibling, current)
            else:
                return False
        return current == normalize_hash(root)
    except (ValueError, KeyError):
        return False


# ── Path normalisation utilities ───────────────────────────────────


def normalize_relative_path(rel: str | Path) -> str:
    """Return a POSIX-style relative path with backslashes replaced and no leading ./"""
    s = str(rel).replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


def sort_key(rel: str | Path) -> str:
    """Sorting key: normalised relative path, lowercase for determinism."""
    return normalize_relative_path(rel).lower()
