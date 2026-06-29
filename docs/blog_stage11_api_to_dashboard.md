# From API to Dashboard: Building a Local Web Interface for Blockchain Evidence

> This is part of a series documenting the construction of a Proof-of-Existence
> system on the Ethereum Sepolia testnet, built as a learning project in
> Solidity, Python, and Web3 development.

---

**Stage 10 made the system callable. Stage 11 makes it usable.** The evidence
toolkit now has a browser interface — and the proof model didn't change at all.

---

## Where We Left Off

Stage 10 wrapped the entire Proof-of-Existence toolkit in a local FastAPI
service. Instead of running CLI commands, any program could now call the
evidence system over HTTP:

```bash
curl -F "file=@works/paper.pdf" http://127.0.0.1:8000/register/file
# { "status": "ok", "file_hash": "0x…", "transaction_hash": "0x…", … }
```

Twenty endpoints, a Swagger UI at `/docs`, typed request validation, and a
uniform `{"status": "ok"}` / `{"status": "error"}` envelope on every response.

By the end of Stage 10 the system could be called by:

- `curl` at the terminal
- `httpx` in a Python test suite
- Another service over the local network
- A CI pipeline

But none of those are a person sitting in front of a browser. An API endpoint
tells a program what happened. A web page tells a human.

So the problem left for Stage 11 isn't about proofs. It isn't about
cryptography. It's about **interface**.

---

## The Gap Between Callable and Usable

Here is the kind of thing a non-developer stakeholder needs to do:

> "I want to register this PDF as evidence and get a certificate I can
> download."

With Stage 10 alone, the answer is: install Python, create a virtual
environment, set up a `.env` file with blockchain credentials, learn the API
contract, construct a `multipart/form-data` POST request, parse the JSON
response, extract the certificate path, and download the file manually.

That is not an answer. That is a barrier.

Stage 11 collapses that barrier into: open a browser, click Register, upload
the file, click Download.

```
Before Stage 11:  a developer with curl.
After Stage 11:   anyone with a browser.
```

---

## Architecture: Adding a Layer, Not Rewriting

The cleanest insight about Stage 11 is that it does not add any new evidence
logic. It adds a new *presentation layer* on top of existing logic.

Stage 10 architecture:

```
Browser / curl
  → FastAPI JSON endpoints (routes_*.py)
  → api/services.py          ← adapter, calls proof_client functions
  → proof_client/            ← core: hash, register, verify, IPFS, crypto, Merkle
```

Stage 11 architecture:

```
Browser
  → FastAPI HTML pages (routes_dashboard.py)   ← new
  → api/services.py                            ← unchanged
  → proof_client/                              ← unchanged
```

The service adapter (`api/services.py`) was already doing the heavy lifting —
converting `UploadFile` inputs to `Path` arguments, calling the right
`proof_client` function, and returning a plain dict. All Stage 11 does is call
those same functions and pass the dict to a Jinja2 template instead of
returning JSON.

The dashboard routes are thin:

```python
@router.post("/dashboard/register")
async def register_submit(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    mode: str = Form("normal"),
    password: str = Form(""),
):
    saved = services.save_upload(file.file, file.filename)
    result = services.register_file_workflow(saved, title=title, ...)
    result.pop("password", None)
    return templates.TemplateResponse(
        request=request, name="result.html", context={"result": result}
    )
```

No business logic. No blockchain calls. No encryption. Just: save the upload,
call the service, render the template.

---

## Why FastAPI + Jinja2 + Bootstrap (and Not React)

The obvious question when building any web UI in 2024 is: why not React? Or
Vue? Or Next.js?

For a local development dashboard, the answer is cost of complexity:

| Factor | React/Vue | Jinja2 + Bootstrap CDN |
|---|---|---|
| Requires Node.js | Yes | No |
| Requires npm | Yes | No |
| Build step | Yes (webpack/vite) | No |
| New language layer | TypeScript/JSX | HTML + Jinja2 tags |
| Backend integration | Separate API calls | In-process, same Python process |
| Time to first page | Hours (setup) | Minutes (one import) |

The project already runs on Python. Adding Jinja2 is one line in
`requirements.txt` and two lines of code:

```python
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="web/templates")
```

Bootstrap from CDN adds professional styling with zero build infrastructure.

If this project ever becomes a public SaaS product, the Stage 10 API endpoints
are already the right interface for a React frontend to consume. The choice of
Jinja2 now does not foreclose React later.

---

## The Pages

Nine pages cover the complete evidence workflow:

```
GET /                          Home — overview with action cards
GET /dashboard/hash            Upload → SHA-256 (no blockchain)
GET /dashboard/register        Upload → register (3 modes)
GET /dashboard/verify          Upload → PASSED / FAILED
GET /dashboard/verify-merkle   Upload file + proof.json → verified
GET /dashboard/evidence        Browse evidence records (SQLite)
GET /dashboard/evidence/{hash} Detail for one record
GET /dashboard/batches         Browse Merkle batch records
GET /dashboard/batches/{id}    Detail for one batch
GET /dashboard/packages        List and download ZIP packages
```

Each POST route accepts a multipart form, calls the corresponding service
function, and renders either `result.html` (success) or `error.html` (failure).

The registration page has one piece of client-side JavaScript — not for a
framework, just to show and hide the password field based on the selected mode:

```javascript
function togglePassword() {
  const mode = document.getElementById('mode').value;
  document.getElementById('password-group').style.display =
    (mode === 'encrypted_ipfs') ? '' : 'none';
}
```

Everything else is server-rendered.

---

## A Bug That Starlette 1.3.1 Introduced

The first run of the test suite produced this error for every page:

```
TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')
```

The traceback pointed here:

```
template = self.cache.get(cache_key)
return self[key]
rv = self._mapping[key]
TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')
```

Jinja2's template cache was receiving a dict as a key — which is not hashable.
That meant the template *name* was being passed a dict, not a string. But the
template name is clearly a string in the code. What went wrong?

The answer: **Starlette changed the `TemplateResponse` API in version 0.27+**.

The old API (Starlette ≤ 0.26):

```python
templates.TemplateResponse(
    "index.html",                   # name (str) — first arg
    {"request": request, ...},      # context dict — second arg
)
```

The new API (Starlette ≥ 0.27, including 1.3.x):

```python
templates.TemplateResponse(
    request=request,                # Request object — first arg
    name="index.html",              # name (str) — second arg
    context={...},                  # context dict — third arg (optional)
)
```

My code was using the old calling convention. Starlette was receiving the string
`"index.html"` as the `request` argument and the context dict as the `name`
argument. Jinja2 then tried to use the dict as a cache key — hence the error.

The fix was straightforward once the root cause was clear:

```python
# Old — broken on Starlette 1.3.x
templates.TemplateResponse("result.html", {"request": request, "result": result})

# New — correct on Starlette 1.3.x
templates.TemplateResponse(request=request, name="result.html", context={"result": result})
```

The static files worked fine during this debugging session — which confirmed the
path and directory setup were correct, isolating the failure to the template
rendering call itself.

The lesson: when an upgrade breaks a working pattern, read the changelog
carefully. Starlette's `TemplateResponse` signature changed signature in a way
that is silently accepted by Python (both forms are valid positional arguments)
but produces completely wrong runtime behavior.

---

## A Second Template Bug: Conditional Logic With `result.passed`

After the API fix, 76 of 78 tests passed. Two failed:

```
❌ T35 PASSED appears in result
❌ T36 unregistered → FAILED in result
```

The result page was rendering "Success" for a verified file instead of "PASSED"
or "FAILED".

The original template logic was:

```html
{% if result.status == "ok" %}
  <span class="badge bg-success">✓ Success</span>
{% elif result.passed is not none %}
  {% if result.passed %}
    <span class="badge bg-success">✓ PASSED</span>
  {% else %}
    <span class="badge bg-danger">✗ FAILED</span>
  {% endif %}
{% endif %}
```

The verify result dict contains both `"status": "ok"` and `"passed": True`.
Because `result.status == "ok"` is checked first, the `elif` branch for `passed`
is never reached. The page always shows "Success" even for a verification result.

The fix: check `passed` first. In Jinja2, `result.passed is defined` returns
`True` if the key exists in the dict (i.e., it is not Jinja2's `Undefined`),
and `False` if the key is absent:

```html
{% if result.passed is defined %}
  {% if result.passed %}
    <span class="badge bg-success">✓ PASSED</span>
  {% else %}
    <span class="badge bg-danger">✗ FAILED</span>
  {% endif %}
{% elif result.status == "ok" %}
  <span class="badge bg-success">✓ Success</span>
{% endif %}
```

Now: a verify result (has `passed`) shows PASSED or FAILED. A register result
(no `passed` key) falls through to the "Success" branch.

---

## Security Design: What Local-Only Means Concretely

The dashboard header warns: "Local development only — do not expose to the
public internet." That warning is load-bearing. Here is what it is protecting
against:

**Encryption passwords in POST form data.** The encrypted-IPFS registration
form accepts a password. That password:
- Is passed to the encryption function in memory
- Is never written to any log
- Is never returned in the response HTML (the test suite asserts this directly)
- Is never stored anywhere after the request completes

**Package downloads via the existing safe endpoint.** The packages page links
to `/packages/{name}`, which is the Stage 10 endpoint. That endpoint:
- Rejects names containing `..`, `/`, or `\`
- Resolves the path and confirms it stays inside `PACKAGES_DIR`
- Returns 400 for anything that would escape the directory

The dashboard does not implement its own download logic — it reuses the
already-tested safe endpoint.

**No private key in any rendered page.** Every GET page was tested to confirm
the wallet private key (from `.env`) does not appear in the HTML output.

What the dashboard does *not* provide: authentication, session management, rate
limiting, HTTPS. Those are not omissions; they are scope decisions for a local
development tool. A production deployment would need all of them.

---

## Testing the Dashboard Without a Blockchain

The test architecture is identical to Stage 10: redirect all file I/O to a temp
directory, monkeypatch the blockchain seams, run everything offline.

```python
# At import time — before the app handles any request
config.UPLOADS_DIR    = _TMP / "uploads"
config.PACKAGES_DIR   = _TMP / "packages"
config.EVIDENCE_DIR   = _TMP / "evidence"
repo.DB_PATH          = _TMP / "evidence.db"

register_mod.register_hash = lambda file_hash, uri: dict(_MOCK_TX)
register_mod.get_address   = lambda: _MOCK_ADDR
verify_mod.verify_hash     = lambda h: {"registered": True, ...}
```

The test suite covers 13 sections across 78 tests:

1. All nine GET pages return 200 with HTML
2. Navbar links present on every page
3. File hash form: result contains the correct SHA-256
4. Register form: three modes, password absent from HTML
5. Verify form: PASSED and FAILED badges render correctly
6. Merkle proof form: proof verification result displayed
7. Evidence list and detail pages
8. Batch list and detail pages
9. Packages page: ZIP listing and `/packages/{name}` download links
10. Static CSS and JS served at `/static/`
11. Security: no private key in HTML, password not in result, path traversal blocked
12. Result page quality: hash-text class, status badges
13. Backward compatibility: all 20 Stage 10 API endpoints still return correct responses

All 78 tests pass, all 90 Stage 10 tests still pass. 545 total tests green.

---

## What the System Looks Like Now

```
Stages 1–4:   file → hash → register → verify
Stage 5:      evidence JSON, SQLite, batch register, Markdown report
Stage 6:      PDF certificate, package ZIP, manifest, verification guide
Stage 7:      IPFS content addressing (file retrievable by CID)
Stage 8:      AES-256-GCM encrypt before IPFS (only ciphertext on public network)
Stage 9:      Merkle batch — N files, 1 root, 1 transaction, 1 proof per file
Stage 10:     FastAPI local service — callable by any program over HTTP
Stage 11:     Web dashboard — usable by any person in a browser
```

Each stage added one capability without breaking the ones before it. The smart
contract hasn't changed since Stage 4. The `register_file()` function in
`proof_client/` is the same function it was in Stage 5. The blockchain proof
model is unchanged.

What changed is the surface area of who can reach it.

---

## Core Sentence

> Stage 10 makes the system callable.
> Stage 11 makes it usable.
>
> The dashboard does not change what the evidence system proves.
> It changes who can use it.
