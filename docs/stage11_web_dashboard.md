# Stage 11: Web Evidence Dashboard

## Why a Web Dashboard?

Stage 10 wrapped the proof_client CLI toolkit in a FastAPI service, making the
evidence system machine-callable.  Stage 11 adds a browser-based interface on
top of that service, making it human-usable.

The key insight is that API usability and UI usability are different problems.
A developer can compose curl commands; most stakeholders cannot.  The dashboard
solves the second problem without touching the first.

## Relationship Between Stage 10 API and Stage 11 UI

```
Browser
  ↓  GET /  |  POST /dashboard/register  |  …
FastAPI HTML routes  (api/routes_dashboard.py)
  ↓  services.*_workflow()
api/services.py  (adapter)
  ↓
proof_client/  (unchanged core logic)
```

Stage 11 adds exactly one new layer: Jinja2 HTML templates served by new
FastAPI routes.  The blockchain, IPFS, crypto, evidence DB, and package export
logic are all untouched.

## Dashboard Architecture

| Layer | Path | Purpose |
|---|---|---|
| Templates | `web/templates/` | Jinja2 HTML (Bootstrap CDN) |
| Static assets | `web/static/` | Custom CSS + copy-to-clipboard JS |
| Dashboard routes | `api/routes_dashboard.py` | URL handlers → template responses |
| Service adapter | `api/services.py` | Unchanged from Stage 10 |
| Core toolkit | `proof_client/` | Unchanged from Stages 1–9 |

## Page and Route Overview

| Page | GET | POST |
|---|---|---|
| Home | `GET /` | — |
| File Hash | `GET /dashboard/hash` | `POST /dashboard/hash` |
| Register | `GET /dashboard/register` | `POST /dashboard/register` |
| Verify File | `GET /dashboard/verify` | `POST /dashboard/verify` |
| Merkle Proof | `GET /dashboard/verify-merkle` | `POST /dashboard/verify-merkle` |
| Evidence List | `GET /dashboard/evidence` | — |
| Evidence Detail | `GET /dashboard/evidence/{file_hash}` | — |
| Batch List | `GET /dashboard/batches` | — |
| Batch Detail | `GET /dashboard/batches/{batch_id}` | — |
| Packages | `GET /dashboard/packages` | — |

## File Hash Workflow

1. User navigates to `/dashboard/hash`
2. Uploads any file
3. Dashboard calls `services.hash_workflow(saved_path)`
4. Result page shows file name, size, SHA-256 hash, and a copy button

No blockchain interaction occurs.

## Registration Workflow

1. Navigate to `/dashboard/register`
2. Upload file, fill optional title/author/description
3. Select mode: **Normal**, **IPFS**, or **Encrypted IPFS**
4. For Encrypted IPFS, enter an encryption password (never stored/returned)
5. Dashboard calls `services.register_file_workflow(...)` with the appropriate flags
6. Result page shows file hash, transaction hash, block number, explorer link

### Mode mapping

| Mode | `upload_ipfs` | `encrypt_before_ipfs` |
|---|---|---|
| normal | False | False |
| ipfs | True | False |
| encrypted_ipfs | True | True |

## Verification Workflow

1. Navigate to `/dashboard/verify`
2. Upload the file to verify
3. Dashboard calls `services.verify_file_workflow(saved_path)`
4. Result page shows PASSED or FAILED badge with on-chain data

## Merkle Proof Workflow

1. Navigate to `/dashboard/verify-merkle`
2. Upload the target file and its `*.proof.json`
3. Optionally check the Merkle root on-chain
4. Dashboard calls `services.verify_merkle_proof_workflow(...)`
5. Result page shows proof verification and optional blockchain status

## Evidence Browser

`GET /dashboard/evidence` lists all single-file evidence records from the local
SQLite database (up to 50).  Each row links to the detail page
(`/dashboard/evidence/{file_hash}`) which shows the full `EvidenceRecord`
fields, with monospace formatting and copy buttons for hash values.

## Batch Browser

`GET /dashboard/batches` lists Merkle batch records (up to 50).  Each row links
to `/dashboard/batches/{batch_id}` showing full batch metadata and, if
available, the list of included files.

## Package Download

`GET /dashboard/packages` lists ZIP archives from `PACKAGES_DIR` (single-file
packages) and `BATCH_PACKAGES_DIR` (batch packages).  Download links for
single-file packages use the existing safe Stage 10 endpoint
`/packages/{package_name}`, which enforces strict path-traversal guards.

## Static Assets

| File | Purpose |
|---|---|
| `web/static/css/style.css` | Custom styles (`.hash-text`, `.status-ok`, etc.) |
| `web/static/js/app.js` | `copyText()` helper for clipboard copy buttons |

Mounted at `/static` via FastAPI's `StaticFiles`.

## Security Boundary

> **This dashboard is designed for local development and demonstration only.**
> It does not implement authentication, rate limiting, or session management.
> **Do not expose it directly to the public internet.**

The dashboard can:

- Trigger on-chain transactions (using the private key from `.env`)
- Read local files and the evidence database
- Export evidence packages
- Handle plaintext encryption passwords in POST form data

All of these require the server to be trusted.  In a production deployment,
authentication middleware would need to be added before this dashboard is
exposed beyond localhost.

## Testing Strategy

The test suite (`api/test_stage11_dashboard.py`) has 78 tests grouped into:

1. **Page rendering** — all GET routes return 200 with HTML content
2. **Navbar** — navigation links present on every page
3. **Hash form** — upload → hash computed and displayed
4. **Register form** — three modes, password not in response
5. **Verify form** — PASSED/FAILED badges rendered correctly
6. **Merkle proof form** — proof verification result shown
7. **Evidence browser** — list and detail pages
8. **Batch browser** — list and detail pages
9. **Packages page** — ZIP listing and download links
10. **Static assets** — CSS and JS served correctly
11. **Security** — no private key or password leaks, path traversal blocked
12. **Result quality** — badges, monospace classes, hash display
13. **Backward compatibility** — all Stage 10 API endpoints still work

Run:
```bash
cd python-client
PYTHONPATH=. .venv/bin/python -m api.test_stage11_dashboard
```

## Future Frontend Options

The Jinja2/Bootstrap dashboard is intentionally simple.  When richer
interactivity is needed, the next step would be a React or Vue SPA that
consumes the Stage 10 API endpoints.  The API layer already provides
everything such a frontend would need.
