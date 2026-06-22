# Stage 6 — Evidence Package System

> Status: shipped in **v0.6.0**
> Scope: `proof_client` PDF certificates, ZIP evidence packages, SHA-256 manifests,
> third-party verification guides, and an integrity-verification CLI.

## 1. Why this stage exists

Stages 1–5 produced an on-chain proof of existence: a file's SHA-256 hash registered
in the `ProofOfExistence` smart contract, plus a local evidence record (JSON + SQLite)
and a Markdown report.

That is enough for *you* to prove something — but not enough to *hand someone else
a single artifact they can independently check*. A proof is only useful if a third
party can verify it **without trusting the issuer and without running this software**.

Stage 6 closes that gap. It packages everything needed for independent verification
into one self-contained, tamper-evident ZIP file:

- the original work file,
- a machine-readable evidence record,
- human-readable certificates (Markdown + PDF),
- a verification guide written for someone who has never seen this project,
- a manifest of SHA-256 checksums that makes any modification detectable.

## 2. Package structure

A package is a directory (and a matching `.zip`) named
`evidence_package_<YYYYMMDD>_<hash8>/`:

```
evidence_package_20260622_abcdef12/
├── original/
│   └── whitepaper.pdf                  # copy of the registered work file
├── evidence/
│   └── evidence_abcdef12.json          # machine-readable on-chain evidence record
├── reports/
│   ├── proof_report_abcdef12.md        # human-readable Markdown certificate
│   └── proof_report_abcdef12.pdf       # human-readable PDF certificate
├── verification/
│   ├── verification_guide.md           # step-by-step third-party verification guide
│   └── verification_commands.txt       # copy-pasteable shell commands
├── manifest.json                       # SHA-256 checksum of every file above
└── README.md                           # package overview + quick verification steps
```

If the original work file can no longer be found at packaging time, `original/`
receives a placeholder that records the expected SHA-256 instead — the package is
still structurally complete and the absence is explicit rather than silent.

## 3. Components

| Module | Responsibility |
|--------|----------------|
| `report_template.py` | Single source of truth for certificate **content**. Both the Markdown and PDF certificates are built from `build_certificate_data()`, so the two formats can never drift apart. |
| `pdf_report.py` | Renders the PDF certificate (ReportLab). |
| `generate_report.py` | Renders the Markdown certificate. |
| `verification_guide.py` | Generates `verification_guide.md` and `verification_commands.txt`, including ready-to-run web3.py / ethers.js snippets and block-explorer steps. |
| `manifest.py` | Builds `manifest.json`, computes a SHA-256 for every file, and verifies a package — both as an extracted directory and **directly inside a ZIP** (no extraction needed). |
| `package_exporter.py` | Orchestrates assembly: copies the original, evidence JSON, reports; writes the verification guide; writes the manifest; writes the package README; and zips it. |
| `export_package.py` | CLI front-end (`--hash` / `--id` / `--all`). |
| `verify_package.py` | CLI front-end for integrity verification. |

### A subtlety: the manifest covers the PDF, but the PDF references the manifest

The PDF certificate displays the `package_manifest_hash`, and the manifest must
also cover the PDF. That is a chicken-and-egg loop. `build_package()` resolves it
in three passes:

1. write the manifest once to obtain `manifest_hash`;
2. regenerate the PDF embedding that `manifest_hash`;
3. rewrite the manifest so it covers the final PDF and the package README.

`manifest.json` excludes *itself* from the file list (you cannot hash a file that
contains its own hash), so the manifest's own integrity is anchored by the
`package_manifest_hash` printed inside the signed-looking PDF certificate.

## 4. The verification model

The package is designed so that **none of the trust depends on this software**.
The verification guide walks a third party through three independent checks:

1. **File fingerprint** — recompute `shasum -a 256 original/<file>` and compare to
   the hash in the certificate. One byte changed ⇒ different hash.
2. **On-chain record** — call `verify(fileHash)` on the contract via a block
   explorer, web3.py, or ethers.js. This returns the owner, the immutable block
   timestamp, and the URI — proving the hash existed **at or before that block**.
3. **Package integrity** — `verify_package` recomputes the SHA-256 of every file
   and compares against `manifest.json`, detecting any post-generation tampering.

### What it proves

- The file existed with its exact content **at or before** the recorded block.
- The registration was made by the recorded address.
- The package has not been altered since it was generated.

### What it does *not* prove

- Legal authorship or copyright ownership.
- That the registrant is the original creator.
- Anything requiring notarization or legal proceedings.

These limitations are stated explicitly inside every certificate — this is a
learning/teaching prototype, not a legal product.

## 5. CLI usage

```bash
cd python-client
export PYTHONPATH=.

# Export a package for one registration (by file hash or SQLite row id)
python -m proof_client.export_package --hash 0xabcdef...   # → packages/evidence_package_<date>_<short>.zip
python -m proof_client.export_package --id 1
python -m proof_client.export_package --all                 # one package per evidence record

# Verify integrity — accepts a .zip OR an already-extracted directory
python -m proof_client.verify_package packages/evidence_package_20260622_abcdef12.zip
python -m proof_client.verify_package packages/evidence_package_20260622_abcdef12/
```

Generated packages land in `python-client/packages/` and are git-ignored.

## 6. `manifest.json` example (sanitized)

```json
{
  "package_version": "1.0",
  "generated_at_utc": "2026-06-22T08:20:46Z",
  "package_type": "ProofOfExistenceEvidencePackage",
  "files": [
    { "path": "README.md",                              "sha256": "9273b2f4843f…" },
    { "path": "evidence/evidence_abcdef12.json",         "sha256": "7864cbc90393…" },
    { "path": "original/whitepaper.pdf",                 "sha256": "059363a263c1…" },
    { "path": "reports/proof_report_abcdef12.md",        "sha256": "11c073349cef…" },
    { "path": "reports/proof_report_abcdef12.pdf",       "sha256": "fb4b50260b1e…" },
    { "path": "verification/verification_commands.txt",  "sha256": "dabb3844e616…" },
    { "path": "verification/verification_guide.md",      "sha256": "2a1b7faab4d5…" }
  ]
}
```

## 7. Integrity check in action

Intact package:

```
🔍 Verifying: packages/evidence_package_20260622_abcdef12.zip
✅ All files match manifest.json — package is intact.
```

After a single byte is appended to `original/whitepaper.pdf` (exit code `1`):

```
🔍 Verifying: evidence_package_20260622_abcdef12/
❌ Package integrity check FAILED:
   • Hash mismatch: original/whitepaper.pdf (expected 059363a263c1…, got d0f2cc8bae08…)
```

## 8. Tests

Stage 6 ships its own suite alongside the existing one. Both are offline (no gas,
no network):

```bash
cd python-client && export PYTHONPATH=.
python -m proof_client.test_all       # 49 cases — core client
python -m proof_client.test_stage6    # 90 cases — packaging, manifest, verification
```

On-chain regression (consumes Sepolia gas, run manually):

```bash
python -m proof_client.test_all --chain
```
