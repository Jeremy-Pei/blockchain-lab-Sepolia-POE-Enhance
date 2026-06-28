# From CLI to API: Wrapping a Proof-of-Existence Toolkit with FastAPI

> This is part of a series documenting the construction of a Proof-of-Existence
> system on the Ethereum Sepolia testnet, built as a learning project in
> Solidity, Python, and Web3 development.

---

**Stage 9 made the evidence system scalable. Stage 10 makes it callable.** The
system is no longer only a CLI toolkit — it is now a local evidence service.

---

## Where We Left Off

Stage 9 made the system *scalable*. Instead of paying for one transaction per
file, a Merkle root lets a single transaction anchor an entire batch, while each
file keeps its own independently verifiable proof.

```
Stage 9:
file A hash ──┐
file B hash ──┼── Merkle tree ── root ── register(root)   ← one transaction
file C hash ──┘
```

By the end of Stage 9 the toolkit could do a lot: hash files, register single
files, upload to IPFS, encrypt before upload, register Merkle batches, generate
certificates, and export self-contained evidence packages.

But all of it lived behind the command line:

```bash
python -m proof_client.register_file works/paper.pdf
python -m proof_client.verify_file works/paper.pdf
python -m proof_client.export_package --hash 0x…
```

That is perfect for a developer at a terminal. It is useless for a web page, a
desktop app, or any other program that wants to *call* the evidence system.

So the problem left for Stage 10 isn't about proofs at all. It's about **shape**.

---

## The Goal: Make It Callable

Stage 10 doesn't add a new cryptographic capability. It adds a new *entry
point*: a local HTTP API in front of everything the toolkit already does.

```
Before Stage 10:  a human runs CLI scripts.
After Stage 10:   any program calls the evidence system over HTTP.
```

I chose FastAPI for the obvious reasons — it's native Python (so it can call the
existing code directly), it generates Swagger docs for free, and file uploads
and typed request models are first-class. But the more interesting decision was
architectural: **how do you put an API in front of a pile of CLI scripts
without rewriting them?**

---

## The Temptation to Shell Out (and Why I Didn't)

The lazy option is to have the API run the CLI as a subprocess:

```python
subprocess.run(["python", "-m", "proof_client.register_file", path])  # don't
```

This is tempting and almost always wrong. You lose typed return values, you
parse text output, errors become exit codes, and every call pays process
startup cost. Worse, it pretends the CLI is the real interface when it isn't.

The CLI was never the product. The *functions* were. `register_file()` already
returns an `EvidenceRecord`. `verify_file()` already returns a dict.
`run_batch_registration()` already returns batch metadata. These are reusable
workflow functions that happened to have a `__main__` block bolted on.

So Stage 10 imports them and calls them in-process:

```
HTTP request → routes_*.py → services.py → proof_client/*.py
```

The routes are thin (parse the request, return the result). A small
`services.py` adapter calls the proof_client functions and serialises their
results to plain dicts. The business logic is untouched.

The *only* change I made to existing code was adding one optional, backward-
compatible parameter — `note` — to `register_file()`, so the API could attach
title/author/description metadata to a single-file record. Everything else in
`proof_client/` is exactly as Stage 9 left it, and all 377 prior tests still
pass.

---

## What the API Looks Like

Twenty endpoints, grouped by concern:

```
GET  /health                          GET  /evidence/files
GET  /version                         GET  /evidence/files/{hash}
POST /files/hash                      GET  /evidence/tx/{tx}
POST /register/file                   GET  /evidence/batches
POST /register/file/ipfs              POST /packages/export
POST /register/file/encrypted-ipfs    GET  /packages/{name}
POST /verify/file                     POST /batches/merkle/register
POST /verify/merkle-proof             POST /batches/merkle/verify
```

And because it's FastAPI, the interactive docs come for free:

```bash
cd python-client
PYTHONPATH=. .venv/bin/uvicorn api.main:app --reload
# open http://127.0.0.1:8000/docs
```

A round trip is now a `curl`:

```bash
curl -F "file=@works/sample_work.txt" http://127.0.0.1:8000/files/hash
# { "status": "ok", "file_hash": "0x…", "file_size_bytes": 42, … }
```

---

## Three Things That Mattered More Than the Endpoints

### 1. A uniform response envelope

Every success returns `{"status": "ok", …}`; every failure returns
`{"status": "error", "message": …}`. I installed exception handlers for both
`HTTPException` and FastAPI's `RequestValidationError` so even a malformed
request comes back in the same shape. A client should never have to guess
whether it's looking at a success or a failure.

### 2. Passwords that go in but never come out

The encrypted-IPFS endpoint accepts a `password` form field. That's a sharp
edge. The rules I enforced — and tested — are simple: the password is never
logged, never returned in the response, and never persisted (only the public
salt/nonce/KDF parameters are kept). One of the security tests literally asserts
the password string does not appear anywhere in the response body.

### 3. A download endpoint that can't be tricked into path traversal

`GET /packages/{name}` serves files from a packages directory. A naive
implementation is a directory-traversal vulnerability waiting to happen. The
endpoint rejects any name containing `..`, `/`, or `\`, and then *resolves* the
path and confirms it still lives inside `PACKAGES_DIR` before serving a byte.

---

## Testing an API Without a Blockchain

The interesting testing problem: registration and verification hit the chain,
and the evidence DB has a `UNIQUE` constraint on file hashes, so naive tests
would either need a live network or fail on the second run.

The solution has two halves. First, **isolation**: at import time the test suite
redirects the evidence DB, the evidence JSON directory, the uploads directory,
and the packages directory to a fresh temp folder. Second, **mocking the
seams**: the blockchain calls (`register_hash`, `verify_hash`, `get_address`)
and the heavy batch pipeline are monkeypatched to return canned values.

Everything that *can* run offline does run for real — the SHA-256 hashing, the
AES-256-GCM encryption, the IPFS `mock` provider, and the full Merkle proof
verification. That keeps the tests honest where it counts and fast where it
doesn't. The result is 90 checks covering health, hashing, registration,
verification, evidence query, batches, packages, security, and backward
compatibility, all green and all offline.

---

## What This Sets Up

Stage 10 is the quiet middle layer between a *tool* and an *application*. There's
no UI yet, and that's deliberate. With a clean, documented, tested HTTP surface
in place, Stage 11 can build a Web Evidence Dashboard — upload, register,
verify, browse, download — entirely on top of these endpoints, without ever
reaching back into the proof_client core.

> **Stage 10 turns the proof-of-existence toolkit from a command-line project
> into a local evidence service.**

The proof model didn't change. The way you reach it did.
