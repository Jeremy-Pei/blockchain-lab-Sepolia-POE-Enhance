# Stage 10 — FastAPI Evidence Service

## 1. Why FastAPI?

Through Stage 9 the proof-of-existence toolkit is feature-complete but is only
reachable through the command line:

```bash
python -m proof_client.register_file works/paper.pdf
python -m proof_client.verify_file works/paper.pdf
python -m proof_client.batch_merkle_register works/
```

That is ideal for a developer, but it cannot be called by a web page, a desktop
app, another service, or (eventually) a mobile client. Stage 10 adds a single,
uniform entry point in front of the existing capabilities: a **local FastAPI
service**.

FastAPI fits this stage because it is:

1. Native Python — it calls the existing `proof_client` code directly.
2. Self-documenting — it generates OpenAPI / Swagger docs at `/docs`.
3. Multipart-friendly — file uploads are first-class.
4. Typed — Pydantic models describe each request and response.
5. Easy to test — `fastapi.testclient.TestClient` drives it in-process.

Stage 10 does **not** change the proof model, the smart contract, the ABI, or
any on-chain logic. It is purely a new service layer.

---

## 2. From CLI to a Service

The key architectural idea is that the CLI modules already contain reusable
workflow functions. The API does **not** shell out to the CLI; it imports and
calls those functions in-process:

```
HTTP request
   │
   ▼
api/routes_*.py        ← thin: parse request, return result
   │
   ▼
api/services.py        ← adapter: call proof_client, serialise to dict
   │
   ▼
proof_client/*.py      ← unchanged business logic (hash / register / verify / …)
   │
   ▼
SQLite + JSON evidence, IPFS, Sepolia
```

Reused functions:

| Capability        | Reused function                                            |
|-------------------|-----------------------------------------------------------|
| Hash              | `proof_client.hash_file.sha256_hash`                      |
| Register          | `proof_client.register_file.register_file`               |
| Verify (file)     | `proof_client.verify_file.verify_file`                   |
| Verify (Merkle)   | `proof_client.verify_merkle_proof.verify_file_against_proof` |
| Export package    | `proof_client.package_exporter.export_by_hash`           |
| Batch register    | `proof_client.batch_merkle_register.run_batch_registration` |
| Evidence query    | `proof_client.evidence_repository` (`find_*` / `list_*`) |

The only change to existing code is a backward-compatible optional `note`
parameter on `register_file()` so the API can carry title / author /
description metadata onto a single-file evidence record.

---

## 3. API Boundaries (what Stage 10 is and isn't)

Stage 10 is intentionally **local-first**. It does:

- run locally and bind to `127.0.0.1`,
- accept local file uploads,
- read and write the local `evidence.db`, `evidence/`, `packages/`, `reports/`,
- talk to whichever network the `.env` configures (Sepolia / Anvil / mock).

It does **not** (yet) implement: user accounts, login, multi-tenant
permissions, public deployment, cloud storage, payments, or a front-end. Those
belong to later stages (Stage 11 — Web Dashboard).

---

## 4. Endpoint Overview

| Method & Path                       | Purpose                                   |
|-------------------------------------|-------------------------------------------|
| `GET  /health`                      | Liveness check                            |
| `GET  /version`                     | Version / stage metadata                  |
| `POST /files/hash`                  | Upload a file, return its SHA-256         |
| `POST /register/file`               | Register a file hash on-chain             |
| `POST /register/file/ipfs`          | Upload to IPFS, register `ipfs://<cid>`   |
| `POST /register/file/encrypted-ipfs`| Encrypt locally, upload ciphertext, register |
| `POST /verify/file`                 | Verify a file against chain + local evidence |
| `POST /verify/merkle-proof`         | Verify a file belongs to a Merkle batch   |
| `GET  /evidence/files`              | List single-file evidence records         |
| `GET  /evidence/files/{file_hash}`  | Lookup evidence by file hash              |
| `GET  /evidence/tx/{tx_hash}`       | Lookup evidence by transaction hash       |
| `GET  /evidence/batches`            | List batch evidence records               |
| `GET  /evidence/batches/{batch_id}` | Lookup batch evidence by id               |
| `POST /packages/export`             | Export a verifiable evidence package      |
| `GET  /packages`                    | List exported package ZIPs                |
| `GET  /packages/{package_name}`     | Download a package ZIP                     |
| `POST /batches/merkle/register`     | Batch Merkle registration of a local folder |
| `POST /batches/merkle/verify`       | Verify a Merkle proof                      |
| `GET  /batches`                     | List batch evidence records               |
| `GET  /batches/{batch_id}`          | Lookup batch evidence by id               |

All responses carry a `status` field: `"ok"` on success, `"error"` on failure.

---

## 5. File Upload Workflow

Uploaded files are streamed to `uploads/` with a sanitised basename (defusing
path traversal in the filename) and then handed to the proof_client functions:

```
POST /files/hash  (multipart: file=@paper.pdf)
   → save to uploads/paper.pdf
   → sha256_hash(uploads/paper.pdf)
   → { "status": "ok", "file_hash": "0x…", "file_size_bytes": …, … }
```

Registration endpoints reuse the same save step, then call
`register_file_workflow(...)`.

---

## 6. Single-File Registration

`POST /register/file` registers the hash with `uri = sepolia://<name>`.
`POST /register/file/ipfs` uploads the plaintext to IPFS first and registers
`ipfs://<cid>`. Both accept optional `title` / `author` / `description` form
fields, stored together on the evidence record's `note`.

The response echoes only public data — file hash, transaction hash, block
number, owner, explorer URL, and (for IPFS) the CID/URI.

---

## 7. Encrypted IPFS Registration

`POST /register/file/encrypted-ipfs` requires a `password` form field. The file
is encrypted locally with AES-256-GCM (Stage 8) and only the **ciphertext** is
uploaded to IPFS; the original file's SHA-256 is still what is registered
on-chain.

Security rules enforced by this endpoint:

- the password is **never** written to logs,
- the password is **never** returned in the response,
- the password is **never** persisted (only public salt / nonce / KDF params).

---

## 8. Evidence Query

Read-only endpoints expose the local SQLite repository. Paths are namespaced
(`/files`, `/tx`, `/batches`) so list endpoints never collide with
by-identifier lookups. Missing records return `404` in the unified error
envelope.

---

## 9. Package Export & Download

`POST /packages/export` builds the full verifiable package (directory + ZIP)
for a registered hash and returns its name and paths. `GET /packages` lists ZIPs
and `GET /packages/{name}` downloads one.

The download endpoint is path-traversal safe: any name containing `..`, `/`, or
`\` is rejected with `400`, and the resolved path is confirmed to live inside
`PACKAGES_DIR` before any file is served.

---

## 10. Merkle Batch API

`POST /batches/merkle/register` takes a local `folder_path` (local-first), an
optional `recursive` flag, and a `dry_run` flag, and runs the Stage 9 pipeline.
`POST /batches/merkle/verify` verifies a file + proof JSON. A future Web
Dashboard can add ZIP-upload batching on top of this.

---

## 11. Security Limitations

This FastAPI service is designed as a **local development service**. It can:

- trigger on-chain transactions,
- read local files and the `.env` private key,
- handle encryption passwords supplied in request forms,
- export and serve evidence packages.

It does **not** implement authentication, authorization, rate limiting, or
hardened input validation.

> Do not expose this API to the public internet without adding authentication,
> rate limiting, file validation, and secure key management.

---

## 12. Testing Strategy

`api/test_stage10_api.py` drives the app with `TestClient`. It isolates state by
redirecting the evidence DB, evidence dir, uploads dir and packages dir to a
temporary directory, and mocks the blockchain seams (`register_hash`,
`verify_hash`, `get_address`) and the heavy batch pipeline. The IPFS `mock`
provider and all encryption run for real because they are local and offline.

Test groups: Health, File hash, Register, Verify, Merkle proof, Evidence query,
Batch, Package, Security boundary, and Error handling / backward compatibility
(90 checks).

Run it:

```bash
cd python-client
PYTHONPATH=. .venv/bin/python -m api.test_stage10_api
```

---

## 13. Future: Web Dashboard

Stage 10 turns the toolkit into a callable service. Stage 11 can build a Web
Evidence Dashboard on top of these endpoints — upload, register, verify, browse
evidence, and download packages from the browser — without touching the
proof_client core again.

---

## 14. Summary

> **Stage 10 changes the system's *form*, not its *proof model*.**

Before Stage 10 a developer ran CLI scripts. After Stage 10 any program can
drive the evidence system over HTTP — while every previous stage's behaviour,
contract, and tests remain fully intact.
