# Stage 8 — Encrypted IPFS Upload (Privacy-Preserving Off-Chain Storage)

Stage 7 gave every registered file a content-addressed home on IPFS. But public
IPFS is **world-readable**: anyone who learns the CID can fetch the bytes. Stage 8
closes that gap by encrypting a sensitive file **locally, before** it is uploaded,
so a public gateway only ever stores ciphertext — while the blockchain still
anchors the hash of the **original** file.

---

## 1. Why encrypted IPFS?

Stage 7's flow uploads the plaintext:

```
original file → SHA-256 → upload original → ipfs://CID → register(file_hash, ipfs://CID)
```

Stage 8's privacy-preserving flow uploads only ciphertext:

```
original file
  → SHA-256 (original)            ← stays the primary, on-chain evidence hash
  → encrypt locally (AES-256-GCM)
  → SHA-256 (ciphertext)
  → upload CIPHERTEXT to IPFS
  → ipfs://CID (of the ciphertext)
  → register(original_file_hash, encrypted ipfs://CID)
  → evidence stores encryption metadata (salt, nonce, KDF — never the password)
```

A verifier downloads the ciphertext, decrypts it with the password, recomputes
the original SHA-256, and confirms it matches the on-chain hash.

---

## 2. Public IPFS risk

IPFS is content-addressed but **not** confidential. There is no access control: a
CID is a capability, and CIDs leak (gateways, logs, the `uri` field on-chain).
Pinning a private manuscript, dataset, or contract in plaintext exposes it
permanently — IPFS content is designed to be replicated and cached.

---

## 3. Threat model

| Actor | Capability | Stage 8 protection |
|-------|-----------|--------------------|
| Passive observer with the CID | Can fetch the stored bytes | Sees only ciphertext |
| Network eavesdropper | Observes the upload | Sees only ciphertext |
| Future CID leak | Bytes already replicated | Still only ciphertext |
| Holder of the password | Can decrypt | **Intended** — this is the verifier |

The scheme assumes the password is shared **out-of-band** with intended verifiers
and is never committed to this system.

---

## 4. What encryption protects

- The **content** of the file (its bytes).

## 5. What encryption does **not** protect

Encryption hides the bytes, nothing else. It does **not** hide:

- the wallet address that registered the hash
- the on-chain transaction time
- the IPFS CID itself
- the (approximate) encrypted file size
- the fact that an upload happened

It is also **not** a substitute for professional legal or security review.

---

## 6. Workflow

```bash
cd python-client
export PYTHONPATH=.

# Encrypt a file locally (prompts for a password, never takes it from argv)
python -m proof_client.encrypt_file works/my_paper.pdf \
    --output encrypted/my_paper.pdf.enc

# Decrypt it again (prompts for the password)
python -m proof_client.decrypt_file encrypted/my_paper.pdf.enc \
    --metadata encrypted/my_paper.pdf.enc.metadata.json \
    --output decrypted/my_paper.pdf

# Register on-chain AND upload an ENCRYPTED copy in one step.
# The original file hash is registered; the uri becomes the ciphertext's CID.
python -m proof_client.register_file works/my_paper.pdf \
    --upload-ipfs --encrypt-before-ipfs
```

`--encrypt-before-ipfs` **requires** `--upload-ipfs` (nothing is encrypted without
an upload). Passing it alone is rejected.

---

## 7. Evidence record fields

Stage 8 adds optional, backward-compatible fields to `EvidenceRecord` (and matching
SQLite columns, migrated in automatically). Older evidence JSON without these keys
still loads cleanly.

| Field | Meaning |
|-------|---------|
| `is_encrypted` | `True` if the uploaded copy is encrypted |
| `encryption_algorithm` | `AES-256-GCM` |
| `encryption_kdf` | `PBKDF2-HMAC-SHA256` |
| `encryption_kdf_iterations` | e.g. `600000` |
| `encryption_salt_hex` | random per-file salt (public) |
| `encryption_nonce_hex` | random per-file AES-GCM nonce (public) |
| `encrypted_file_hash` | SHA-256 of the **ciphertext** |
| `encrypted_file_name` | ciphertext filename (`*.enc`) |
| `encrypted_ipfs_cid` / `_uri` / `_gateway_url` | IPFS pointers to the ciphertext |
| `encrypted_ipfs_provider` / `_uploaded_at` | provider + timestamp |

**Invariant:** `file_hash` is always the **original plaintext** SHA-256 — the
primary evidence hash and what is registered on-chain. `encrypted_file_hash` only
identifies the blob stored on IPFS and never replaces it.

The password and the derived key are **never** stored in any field.

---

## 8. Verification workflow

```bash
# Automated — looks everything up from stored evidence by the original hash
python -m proof_client.verify_encrypted_ipfs --hash 0x<original_file_hash>

# Manual equivalent
python -m proof_client.ipfs_download <encrypted_cid> -o downloads/encrypted_file.enc
python -m proof_client.decrypt_file downloads/encrypted_file.enc \
    --metadata encrypted/encryption_metadata.json \
    --output decrypted/recovered_file
shasum -a 256 decrypted/recovered_file   # must equal the original file hash
```

The verifier:

1. downloads the ciphertext by CID,
2. (optionally) confirms its SHA-256 equals `encrypted_file_hash`,
3. decrypts it with the password + stored salt/nonce/KDF,
4. recomputes the decrypted file's SHA-256,
5. compares it with `evidence.file_hash`,
6. queries the contract `verify(file_hash)` and confirms the on-chain `uri` is
   the encrypted CID.

---

## 9. CLI commands

| Command | Purpose |
|---------|---------|
| `encrypt_file` | Encrypt a file locally → `*.enc` + `*.metadata.json` |
| `decrypt_file` | Decrypt a `*.enc` file using its metadata |
| `register_file --upload-ipfs --encrypt-before-ipfs` | Encrypt → upload ciphertext → register original hash |
| `verify_encrypted_ipfs --hash <hash>` | Download, decrypt, recompute, compare |

Evidence packages for an encrypted record gain an `encrypted/` folder
(`encrypted_file.enc` + `encryption_metadata.json`), the certificate gains an
**Encrypted Off-Chain Storage** section, and the verification guide gains
**Step 5 — Verify Encrypted IPFS Content**. By default an encrypted package
**excludes** the plaintext original (use `--include-original` to override;
`--exclude-original` forces exclusion).

---

## 10. Cryptographic design

- **Algorithm:** AES-256-GCM (authenticated encryption — wrong password or any
  tampering of the ciphertext fails loudly on decrypt).
- **Key derivation:** PBKDF2-HMAC-SHA256, 600,000 iterations, 32-byte key.
- **Salt:** 16 random bytes per file. **Nonce:** 12 random bytes per file.
- Salt and nonce are **not secret** — they are stored in the metadata so a holder
  of the password can re-derive the key. The same `(password, salt, iterations)`
  always yields the same key; a different salt yields a different key.

---

## 11. Security limitations

- **The system never stores the password or the encryption key** — not in the
  evidence record, the database, the certificate, or the package.
- **If the password is lost, the encrypted file cannot be recovered by this
  system.** There is no recovery path by design.
- This is an **educational prototype** and has **not** been professionally
  audited. Do not rely on it for high-stakes confidentiality without an
  independent review.

---

## 12. Testing strategy

`test_stage8.py` covers (75 cases):

1. config encryption settings
2. salt / nonce / KDF primitives (lengths, determinism, distinctness)
3. encrypt/decrypt round-trip, wrong password, tampered ciphertext
4. metadata excludes secrets
5. `encrypt_file` / `decrypt_file` CLI helpers
6. `EvidenceRecord` encryption fields + backward compatibility
7. SQLite column migration + insert/read round-trip
8. encrypt-then-upload to mock IPFS
9. `register_file --encrypt-before-ipfs` argument rules
10. `verify_encrypted_ipfs` success / wrong password / mismatch
11. certificate (Markdown + PDF) encrypted section
12. verification guide Step 5
13. evidence package `encrypted/` folder + original-inclusion policy
14. security invariants — passwords/keys never persisted

```bash
cd python-client
PYTHONPATH=. .venv/bin/python -m proof_client.test_stage8
# and the regression suites:
PYTHONPATH=. .venv/bin/python -m proof_client.test_all
PYTHONPATH=. .venv/bin/python -m proof_client.test_stage6
PYTHONPATH=. .venv/bin/python -m proof_client.test_stage7
```
