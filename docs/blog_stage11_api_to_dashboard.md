# From API to Dashboard: Building a Local Web Interface for Blockchain Evidence

> Stage 10 made the system callable.
> Stage 11 makes it usable.

## The Problem With APIs

After Stage 10, the Proof-of-Existence toolkit had a clean FastAPI service.
Developers could curl it, test clients could call it, and CI pipelines could
integrate with it.  But ask a non-technical user to register their research
paper on the blockchain, and the first thing they would say is: "Where do I
click?"

APIs are designed for programs.  Dashboards are designed for people.  Stage 11
adds the second without breaking the first.

## What Stage 11 Does Not Do

Before explaining what Stage 11 builds, it is worth being precise about what it
does *not* do:

- It does not change the evidence model
- It does not change the blockchain logic
- It does not change the IPFS integration
- It does not change the encryption scheme
- It does not change the Merkle batch registration
- It does not add authentication

Stage 11 does exactly one thing: it wraps the existing API service in a set of
HTML pages.

## Architecture: Adding a Layer, Not Rewriting

Stage 10 architecture:

```
Browser / curl
  → FastAPI JSON endpoints
  → api/services.py
  → proof_client/
```

Stage 11 architecture:

```
Browser
  → FastAPI HTML pages   (new)
  → api/services.py      (unchanged)
  → proof_client/        (unchanged)
```

The service adapter (`api/services.py`) was already doing the heavy lifting.
The dashboard routes simply call the same service functions and pass the results
to Jinja2 templates instead of returning JSON.

## Technology Choices

The stack for Stage 11 is **FastAPI + Jinja2 + Bootstrap CDN**.

Why not React or Vue?

- The backend is already FastAPI; adding Jinja2 requires one import
- Bootstrap from CDN gives professional-looking UI with no build step
- No Node.js, no npm, no webpack, no TypeScript compiler
- The result is a single Python service that serves both API and UI

This is appropriate for a local development tool.  If the project ever grows
into a SaaS product, the API endpoints from Stage 10 are ready for any
frontend framework to consume.

## Pages Built

The dashboard covers the complete evidence workflow:

1. **Home** (`/`) — overview with cards linking to each section
2. **Hash File** (`/dashboard/hash`) — SHA-256 without blockchain interaction
3. **Register** (`/dashboard/register`) — three modes: plain, IPFS, encrypted IPFS
4. **Verify** (`/dashboard/verify`) — PASSED/FAILED badge with on-chain data
5. **Merkle Proof** (`/dashboard/verify-merkle`) — per-file proof verification
6. **Evidence Browser** (`/dashboard/evidence`) — SQLite-backed record listing
7. **Batch Browser** (`/dashboard/batches`) — Merkle batch records
8. **Packages** (`/dashboard/packages`) — ZIP download listing

## Security Design: Local-First

The dashboard is honest about what it is: a local development tool.  It
declares this prominently in the UI and in the documentation.

Concretely:

- Encryption passwords travel in POST form data and are never stored or returned
- No password appears in any result HTML (asserted by the test suite)
- Package downloads use the existing safe Stage 10 endpoint (which blocks path traversal)
- No private key is exposed in any rendered page

These measures are appropriate for a local tool.  A public deployment would
require HTTPS, authentication, rate limiting, and key management changes beyond
what Stage 11 scopes.

## Testing

The test suite (`test_stage11_dashboard.py`) runs 78 tests:

- All nine GET pages return 200 with HTML
- POST forms submit correctly and render results
- Passwords are absent from response HTML
- Static assets load
- Path traversal remains blocked
- All 90 Stage 10 API tests still pass (backward compatibility)

The test architecture mirrors Stage 10: monkeypatching the blockchain seams so
tests run without network access.

## The Core Insight

Stage 10 made the system callable.  That meant a developer with curl could use
it.

Stage 11 makes it usable.  That means anyone with a browser can use it.

These are different audiences, and serving both is the point.

The blockchain logic did not change.  The evidence model did not change.  The
API did not change.  What changed is the interface layer — and that change
makes the entire system accessible to a much wider group of people.

```
Stage 10: make the system callable
Stage 11: make the system usable
```
