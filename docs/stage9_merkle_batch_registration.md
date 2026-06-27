# Stage 9 — Merkle Root Batch Registration

## 1. Why Merkle Batch Registration?

Previous stages register one file hash per blockchain transaction. When the
number of files grows, this becomes expensive:

| Approach | Files | Transactions |
|----------|-------|-------------|
| Single-file (Stages 1–8) | N | N |
| Merkle batch (Stage 9) | N | 1 |

A Merkle root lets **one blockchain transaction prove a whole batch of files**.
Each file retains its own independently verifiable proof, so no central party
needs to be trusted to confirm membership.

---

## 2. Single-File vs Batch Registration

### Single-file (existing, unchanged)

```
file A → register(hashA)   ← one transaction
file B → register(hashB)   ← one transaction
file C → register(hashC)   ← one transaction
```

### Merkle batch (Stage 9)

```
file A hash ──┐
file B hash ──┼── Merkle tree ── Merkle root ── register(root)  ← one transaction
file C hash ──┘
```

Both modes coexist. The single-file flow in `register_file.py` is unchanged;
`batch_merkle_register.py` is a new, additive capability.

---

## 3. Merkle Tree Rules

These rules must be followed exactly for third-party reproducibility.

| Parameter | Rule |
|-----------|------|
| **Leaf hash algorithm** | SHA-256 of file bytes |
| **Leaf ordering** | Normalised relative path, ascending lexicographic |
| **Internal node** | SHA-256(left\_bytes \|\| right\_bytes) |
| **Odd-level padding** | Duplicate the last node |
| **Hash encoding** | 0x-prefixed lowercase hex string |

All rules are recorded verbatim in each `batch_evidence.json` under the fields
`leaf_hash_algorithm`, `merkle_algorithm`, `leaf_ordering`, and
`odd_leaf_strategy`.

---

## 4. Leaf Ordering and Determinism

The Merkle root depends on the order of leaves. To guarantee that any verifier
who has the same files can reproduce the exact same root, leaves must be sorted
by a stable, canonical key.

**Normalisation rules for relative paths:**

1. Replace backslashes with forward slashes (`\` → `/`)
2. Remove any leading `./`
3. Sort lexicographically (case-insensitive for cross-platform stability)

Examples:

```
image.png
paper.pdf
poem.txt
sub/chapter1.txt
sub/chapter2.txt
```

This ordering is stored in `leaves.json` as `relative_path` values.

---

## 5. Batch Registration Workflow

```
1. Collect files (filter by extension, sort by relative path)
2. Compute SHA-256(file bytes) for each file
3. Build Merkle tree from sorted leaf hashes
4. Compute Merkle root
5. Generate batch_id = batch_<YYYYMMDD_HHMMSS>
6. Call contract.register(merkle_root, "batch://<batch_id>")
7. Write evidence files:
     batch_evidence.json    ← top-level record (record_type = "merkle_batch")
     merkle_tree.json       ← all tree levels
     leaves.json            ← per-file leaf records
     batch_summary.json     ← at-a-glance summary
     proofs/<file>.proof.json  ← one per file
8. Generate Markdown + PDF certificate
9. Insert into SQLite (batch_evidence_records table)
10. Assemble batch evidence package (ZIP)
```

### What is registered on-chain?

```
fileHash parameter = Merkle root   (not a single file hash)
uri parameter      = batch://<batch_id>
```

The smart contract is unchanged — the `fileHash` parameter accepts any
`bytes32` value, and the Merkle root is a valid 32-byte SHA-256 digest. The
`batch_evidence.json` makes the distinction explicit via `record_type = "merkle_batch"`.

---

## 6. Per-File Proof Workflow

Each file in the batch receives a `.proof.json` file in
`evidence/batches/<batch_id>/proofs/`. The proof contains the sibling hashes
and positions needed to recompute the Merkle root from the file's SHA-256
alone.

### Proof item format

```json
{
  "position": "right",
  "hash": "0x..."
}
```

- `position = "right"`: sibling is to the right → compute `SHA-256(current || sibling)`
- `position = "left"`:  sibling is to the left  → compute `SHA-256(sibling || current)`

### Full proof JSON

```json
{
  "proof_type": "merkle_file_proof",
  "batch_id": "batch_20260627_001",
  "file_name": "paper.pdf",
  "relative_path": "paper.pdf",
  "file_hash": "0x...",
  "merkle_root": "0x...",
  "leaf_index": 1,
  "proof": [
    { "position": "left",  "hash": "0x..." },
    { "position": "right", "hash": "0x..." }
  ],
  "network": "Ethereum Sepolia",
  "chain_id": 11155111,
  "contract_address": "0x...",
  "transaction_hash": "0x...",
  "explorer_url": "https://sepolia.etherscan.io/tx/0x..."
}
```

---

## 7. Verification Workflow

### Local verification (no blockchain call)

```bash
python -m proof_client.verify_merkle_proof \
    --file works/paper.pdf \
    --proof evidence/batches/<batch_id>/proofs/paper.pdf.proof.json
```

Steps performed:
1. Recompute `SHA-256(file bytes)`.
2. Compare with `proof.file_hash`.
3. Walk the proof steps to recompute the Merkle root.
4. Compare recomputed root with `proof.merkle_root`.

### With on-chain confirmation

```bash
python -m proof_client.verify_merkle_proof \
    --file works/paper.pdf \
    --proof evidence/batches/<batch_id>/proofs/paper.pdf.proof.json \
    --chain
```

Additional step:
5. Call `contract.verify(merkle_root)` — confirm `timestamp != 0`.

### Manual verification (no software required)

For each proof step `{ position, sibling_hash }`:
- If `position == "right"`: `current = SHA-256(current_bytes || sibling_bytes)`
- If `position == "left"`:  `current = SHA-256(sibling_bytes || current_bytes)`

The final `current` must equal `merkle_root`.

---

## 8. Evidence Package Structure

```
merkle_batch_package_<date>_<short>/
├── original/
│   ├── file_001.txt
│   ├── file_002.pdf
│   └── ...
├── batch/
│   ├── batch_evidence.json   ← record_type = "merkle_batch"
│   ├── merkle_tree.json      ← all levels, root, algorithm metadata
│   ├── leaves.json           ← per-file records (index, path, hash, size)
│   └── batch_summary.json    ← compact at-a-glance summary
├── proofs/
│   ├── file_001.txt.proof.json
│   ├── file_002.pdf.proof.json
│   └── ...
├── reports/
│   ├── batch_certificate.md  ← human-readable Markdown certificate
│   └── batch_certificate.pdf ← professional PDF certificate
├── verification/
│   ├── batch_verification_guide.md   ← step-by-step third-party guide
│   └── verification_commands.txt     ← copy-pasteable commands
├── manifest.json             ← SHA-256 checksum of every file (incl. proofs)
└── README.md
```

The `manifest.json` covers every file in the package, including all `.proof.json`
files, so any post-generation tampering is detectable.

---

## 9. Gas Cost Discussion

Registering a Merkle root uses the same `register(bytes32, string)` call as a
single-file registration. The gas cost per registration is approximately
`~50 000–80 000` gas (fixed overhead of the contract call, plus calldata for
the URI string).

| Batch size | Without batching | With Merkle batching |
|------------|-----------------|----------------------|
| 10 files   | ~10 transactions | 1 transaction |
| 100 files  | ~100 transactions | 1 transaction |
| 1 000 files | ~1 000 transactions | 1 transaction |

The trade-off: a single `merkle_tree.json` and set of `.proof.json` files must
be stored and shared out-of-band (in the evidence package) for any file to be
independently verifiable.

---

## 10. Limitations

- A Merkle proof verifies that a file hash was included in a registered batch
  root. It does not prove legal authorship, copyright ownership, or originality.
- If the proof files are lost, files can still be reverified by rebuilding the
  tree from `leaves.json`.
- The Merkle root `record_type` is declared in `batch_evidence.json`, not
  in the smart contract. Any on-chain observer sees only a `bytes32` value.
- This is an educational prototype and has not been professionally audited.

---

## 11. CLI Examples

```bash
cd python-client
export PYTHONPATH=.

# Basic batch registration
python -m proof_client.batch_merkle_register works/ \
    --title "My Copyright Evidence Batch" \
    --author "Author Name" \
    --description "Batch proof-of-existence for multiple works."

# Recurse into sub-directories
python -m proof_client.batch_merkle_register works/ --recursive

# Dry-run (no blockchain transaction)
python -m proof_client.batch_merkle_register works/ --dry-run

# Verify a single file belongs to a batch (local)
python -m proof_client.verify_merkle_proof \
    --file works/paper.pdf \
    --proof evidence/batches/<batch_id>/proofs/paper.pdf.proof.json

# Verify with on-chain confirmation
python -m proof_client.verify_merkle_proof \
    --file works/paper.pdf \
    --proof evidence/batches/<batch_id>/proofs/paper.pdf.proof.json \
    --chain
```

---

## 12. Testing Strategy

```bash
cd python-client

# Stage 9 test suite (84 tests)
PYTHONPATH=. .venv/bin/python -m proof_client.test_stage9

# All suites (confirms backward compatibility)
PYTHONPATH=. .venv/bin/python -m proof_client.test_all
PYTHONPATH=. .venv/bin/python -m proof_client.test_stage6
PYTHONPATH=. .venv/bin/python -m proof_client.test_stage7
PYTHONPATH=. .venv/bin/python -m proof_client.test_stage8
PYTHONPATH=. .venv/bin/python -m proof_client.test_stage9
```

Test groups in `test_stage9.py`:

| Group | Tests | Coverage |
|-------|-------|----------|
| Merkle tree core | T01–T08 | Build, root, levels, prefixes |
| Proof generation | T09–T13 | All leaves, structure, edge cases |
| Proof failure cases | T14–T18 | Tampered file/root/sibling/direction |
| File ordering | T19–T27 | Normalisation, sort, hidden/unsupported |
| Batch evidence JSON | T28–T43 | All fields, leaves.json, proofs, summary |
| Batch SQLite | T44–T49 | Insert, find by id/root, dedup, count |
| Batch reports | T50–T57 | Markdown content, PDF generation, filename |
| Batch package | T58–T70 | All files, manifest coverage, ZIP |
| CLI tests | T71–T78 | collect_files, verify, URI format, guide |
| Backward compat | T79–T84 | Old records, module exports, config |

---

## 13. Engineering Note — The `lstrip("0x")` Trap in Cryptographic Code

This bug was caught during Stage 9 development. It is a subtle Python pitfall
that corrupts hash values silently and is worth documenting because it can occur
in any code that handles hex-encoded cryptographic data.

### What happened

The first draft of `normalize_hash()` was written as:

```python
def normalize_hash(hex_hash: str) -> str:
    h = hex_hash.lower().lstrip("0x")   # ← BUG
    ...
    return "0x" + h
```

### Why it is wrong

`str.lstrip(chars)` does **not** remove a prefix string. It removes all leading
characters that appear anywhere in the `chars` argument, treating `chars` as a
**set of characters to strip**, not as a literal prefix.

The argument `"0x"` means: *strip any leading character that is either `'0'` or
`'x'`*.

So for the hash:

```
0x0abc1234...
```

`lstrip("0x")` strips `'0'`, then `'x'`, then the next `'0'` — because `'0'`
is still in the strip-set — giving:

```
abc1234...   ← 63 characters instead of 64
```

The leading zero was swallowed. The result is an invalid 63-character hex string
instead of the expected 64. Appending `"0x"` back produces `"0xabc1234..."`,
which represents a completely different 256-bit value.

### Why it matters here

Merkle tree construction concatenates raw bytes from pairs of hashes before
hashing them. A corrupted 63-char hex string decodes to 31.5 bytes — an
error that Python's `bytes.fromhex()` raises immediately. But in languages or
contexts where silent truncation can occur, the corrupted value would silently
produce the wrong tree and the wrong root, making every generated proof
unverifiable without any error message.

In short: **a one-character mistake in a string helper invalidated every
cryptographic output the code produced**.

### The concrete failure observed

The test `T07` fed four single-byte leaf hashes to `build_merkle_tree`. Leaf
index 3 was `SHA-256(\x03)`:

```
0x084fed08b978af4d7d196a7446a86b58009e636b611db16211b65a9aadff29c5
         ^
         leading zero after the 0x prefix
```

`lstrip("0x")` stripped `0x0`, leaving `84fed08...` — 63 characters. The
`normalize_hash` guard immediately raised:

```
ValueError: Expected 64-character hex hash, got 63
```

The error surfaced at the first test that happened to use a hash with a leading
zero after `0x`, which is statistically likely in any real-world SHA-256 output.

### The fix

```python
# Wrong — strips all leading '0' and 'x' characters:
h = hex_hash.lower().lstrip("0x")

# Correct — removes exactly the two-character prefix "0x":
s = hex_hash.lower()
h = s[2:] if s.startswith("0x") else s
```

Or equivalently:

```python
h = hex_hash.lower().removeprefix("0x")   # Python 3.9+, most explicit
```

### The general rule

Whenever you need to remove a **fixed prefix** from a string in Python, use:

| Goal | Correct | Wrong |
|------|---------|-------|
| Remove prefix `"0x"` | `s[2:]` or `s.removeprefix("0x")` | `s.lstrip("0x")` |
| Remove prefix `"0X"` | `s[2:]` after lowercasing | `s.lstrip("0X")` |
| Remove leading zeros only | `s.lstrip("0")` | — |

`lstrip` / `rstrip` / `strip` are **set-based character strippers**, not
**substring removers**. The distinction is invisible when the prefix consists of
unique characters (`"abc"` and `"a"+"b"+"c"` behave the same), but becomes a
silent bug the moment the characters repeat — which is exactly the case with
`"0x"` and a hex string that starts with `0x0`.

### Why cryptographic code is especially vulnerable

- Hash values are fixed-width (SHA-256 = 64 hex chars). Any truncation is a
  hard error, but only if the code validates length. Without the `len(h) != 64`
  guard, the wrong value would propagate silently.
- Leading zeros in SHA-256 outputs occur with probability ~1/16 per nibble.
  Any test suite that doesn't exercise hashes with leading zeros will miss this
  bug entirely.
- The mistake is easy to make because `lstrip("0x")` looks like "remove the
  `0x` prefix" — a plausible reading that Python does not enforce.

---

## 14. Summary

> **A Merkle root proves the batch.
> A Merkle proof proves one file belongs to that batch.**

Stage 9 adds batch proof-of-existence as an additive capability alongside the
unchanged single-file mode. The smart contract, ABI, and all previous
stage features remain fully compatible.
