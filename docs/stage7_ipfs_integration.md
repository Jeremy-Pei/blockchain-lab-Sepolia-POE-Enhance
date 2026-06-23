# Stage 7 — IPFS Integration (Off-Chain Content-Addressed Storage)

> Status: shipped in **v0.7.0**
> Scope: an IPFS storage layer for `proof_client` — upload, download, content
> verification, CLI tools, evidence-record fields, certificate / package /
> verification-guide integration, and a 79-test suite.
> **The smart contract is unchanged.**

## 1. Why IPFS?

Stages 1–6 produced a strong on-chain proof and a self-contained, tamper-evident
evidence package. But a gap remained:

- The blockchain only proves that a **hash** existed at a point in time.
- The evidence package can *carry* the original file — but if that package is
  lost, a third party has no way to **re-obtain the original bytes**.

Stage 7 closes that gap by giving the file (or an encrypted copy of it) a
**content-addressed** home off-chain:

```
original file
  → SHA-256 hash
  → IPFS upload → CID
  → register(fileHash, "ipfs://CID")   ← contract uri field, unchanged
  → evidence record stores the CID
  → certificate / package / verification guide show the CID
```

## 2. What IPFS solves

- A durable, **content-addressed** pointer (`ipfs://<CID>`) to a retrievable copy
  of the file, independent of any single server or this software.
- The on-chain `uri` field finally points at a *real, fetchable* resource instead
  of a local-only path like `sepolia://my_paper.pdf`.

## 3. What IPFS does **not** solve

- It does **not** replace the SHA-256 as the proof hash.
- It does **not** guarantee permanence by itself — content must stay *pinned* by
  at least one node, or it can be garbage-collected.
- It does **not** provide privacy — see §7.

## 4. SHA-256 vs IPFS CID — not the same thing

This distinction is stated everywhere in the system, on purpose:

| | SHA-256 `file_hash` | IPFS `CID` |
|---|---|---|
| Purpose | Proves **which file version** was registered | Identifies **content** in the IPFS network |
| Used by | The smart contract (`bytes32`) and all evidence | The off-chain storage pointer (`uri`) |
| Primary? | **Yes** — the canonical evidence hash | No — a convenience pointer |

> **SHA-256 hash proves the file version in this system. IPFS CID identifies the
> content in the IPFS network. They are related but not identical.**

## 5. Upload workflow

```bash
cd python-client
export PYTHONPATH=.

# Upload only (no chain) — prints CID, ipfs:// URI, gateway URL, SHA-256
python -m proof_client.ipfs_upload works/my_paper.pdf

# Register on-chain AND upload to IPFS in one step
# (the on-chain uri becomes ipfs://<CID> and the CID is stored on the record)
python -m proof_client.register_file works/my_paper.pdf --upload-ipfs
python -m proof_client.register_file works/my_paper.pdf --upload-ipfs --ipfs-provider pinata

# The original local-only flow is untouched
python -m proof_client.register_file works/my_paper.pdf
```

## 6. Verification workflow

The full verification chain becomes:

```
IPFS downloaded file
  → SHA-256
  → compare with evidence file_hash
  → query smart contract verify(file_hash)
  → confirm owner / timestamp / uri
  → compare uri with ipfs://CID
```

```bash
# Download a CID and confirm its SHA-256 matches the registered hash
python -m proof_client.verify_ipfs --cid <CID> --expected-hash 0x<hash>

# Or look the CID + expected hash up from stored evidence
python -m proof_client.verify_ipfs --hash 0x<file_hash>

# Manual equivalent
curl -L "https://ipfs.io/ipfs/<CID>" -o downloaded_file
shasum -a 256 downloaded_file   # must equal the evidence file_hash
```

## 7. Privacy warning ⚠️

**Do not upload private or sensitive files to public IPFS without encryption.**

- A CID can be shared, and public gateways can serve the content to anyone.
- Once a file is pinned by others, deleting it is effectively impossible.
- IPFS is appropriate for **public** files or **encrypted** files — not for raw,
  private originals.

> **For sensitive works, upload an encrypted copy rather than the raw original
> file.** Encrypted upload is planned as a later stage; Stage 7 ships the
> public-file workflow and this warning.

## 8. CLI commands

| Command | Purpose |
|---|---|
| `python -m proof_client.ipfs_upload <file> [--provider]` | Upload a file, print CID / URI / gateway / SHA-256 |
| `python -m proof_client.ipfs_download <cid> -o <path>` | Download a file from IPFS by CID |
| `python -m proof_client.verify_ipfs --cid <cid> --expected-hash <h>` | Verify downloaded content against a hash |
| `python -m proof_client.verify_ipfs --hash <file_hash>` | Verify using CID + hash from stored evidence |
| `python -m proof_client.register_file <file> --upload-ipfs` | Register on-chain and pin to IPFS in one step |

### Providers

Selected by `IPFS_PROVIDER` (or `--ipfs-provider`):

- **`mock`** — a local, network-free content store under `mock_ipfs_storage/`.
  Deterministic and content-addressed (identical bytes → identical CID), so it
  is ideal for tests and offline demos. **Default.**
- **`pinata`** — uploads to the [Pinata](https://www.pinata.cloud/) pinning
  service. Requires `PINATA_JWT` in `.env`; a missing/placeholder key produces a
  clear error rather than a silent failure.

## 9. Evidence record fields (backward compatible)

`EvidenceRecord` gains six optional, defaulted IPFS fields:
`ipfs_cid`, `ipfs_uri`, `ipfs_gateway_url`, `ipfs_provider`, `ipfs_uploaded_at`,
`ipfs_sha256`. Older evidence JSON without these keys still deserialises cleanly,
and the SQLite repository migrates pre-Stage-7 databases by adding the columns
on first open.

## 10. Evidence package additions

When a record carries a CID, the exported package gains an `ipfs/` directory:

```
evidence_package_<date>_<short>/
├── original/
├── evidence/
├── reports/
├── verification/
├── ipfs/
│   ├── ipfs_metadata.json        # CID, ipfs:// URI, gateway URLs, provider, hashes
│   └── ipfs_gateway_links.txt    # browsable links across public gateways
├── manifest.json                 # now also checksums the ipfs/ files
└── README.md
```

The PDF / Markdown certificate gains an **Off-Chain Storage (IPFS)** section, and
the third-party verification guide gains **Step 4 — Verify the IPFS Content**.
Records without a CID show `Not available` / mark Step 4 as not applicable, so
old registrations still produce valid certificates.

## 11. Environment variables

`.env.example` (placeholders only — never commit a real key):

```ini
IPFS_PROVIDER=mock
IPFS_GATEWAY_URL=https://ipfs.io/ipfs/
PINATA_JWT=your_pinata_jwt_here
PINATA_API_URL=https://api.pinata.cloud
```

`.env`, `mock_ipfs_storage/`, and `downloads/` remain git-ignored.

## 12. Testing strategy

`test_stage7.py` adds **79** tests (target was 40+), covering:

- CID validation, `ipfs://` URI and gateway-URL formatting;
- mock upload/download, hash invariance, content-addressing determinism;
- `get_client` factory + Pinata missing-key error;
- `EvidenceRecord` IPFS fields, serialisation, and backward compatibility;
- JSON store + SQLite persistence (incl. schema migration);
- `register_file --upload-ipfs` argument parsing;
- IPFS section in the certificate, PDF, and verification guide;
- `ipfs/` directory + metadata + manifest coverage in the package;
- `verify_ipfs` success, tamper detection, and unknown-CID handling.

```
Core tests:     49
Stage 6 tests:  90
Stage 7 tests:  79
```
