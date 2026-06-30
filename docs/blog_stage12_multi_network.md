# From Single-Chain to Multi-Network: Stage 12 of Our Proof-of-Existence System

*Stage 12 of an ongoing blockchain development series*

---

When I started this project, the Sepolia testnet was hardcoded everywhere: in `.env`, in CLI defaults, in the evidence records written to SQLite, even in the URL templates baked into the dashboard. It worked fine for a single-network prototype, but every time someone asked "can I test this on Anvil first?" or "does it support Base Sepolia?" the answer was an embarrassing dance of manual env var swaps.

Stage 12 fixes that properly.

---

## The Design Principle: Network Config as Data

The cleanest architectural decision I made was to represent each network as a JSON file, not as code. The `networks/` directory now holds three files:

```
python-client/networks/
  anvil.json
  sepolia.json
  base_sepolia.json
```

Each file answers the same set of questions: What's your RPC URL env var? Contract address env var? Chain ID? Explorer URL template? Every network is just a different answer to those same questions.

This means adding a fourth network later — say, Optimism Sepolia — is a config task, not a code change. Create the JSON, set the env vars, deploy the contract. Done.

---

## The NetworkConfig Dataclass: Config vs. Runtime

One subtlety worth calling out: the JSON files describe a network's *structure*, not its *values*. The `rpc_url_env_key` field holds a string like `"SEPOLIA_RPC_URL"` — not the actual RPC URL. The URL is read at runtime via a `@property`:

```python
@property
def rpc_url(self) -> str:
    return os.getenv(self.rpc_url_env_key, "")
```

This keeps secrets out of config files (where they don't belong) while still giving the config layer everything it needs to know about a network at load time. Chain ID validation — comparing what the RPC node reports with what the JSON file says — catches the classic mistake of pointing `SEPOLIA_RPC_URL` at a Base Sepolia endpoint.

---

## Network Resolution Priority

The most user-facing design decision was the resolution order:

1. Explicit `--network` argument (or `network=` form field in the API)
2. The `network_key` stored in the local evidence record *(verify flow only)*
3. The `DEFAULT_NETWORK` environment variable
4. Fall back to `"sepolia"`

The second rule is the subtle one. When you verify a file, you shouldn't have to remember which network you registered it on. The evidence record stores that. If you registered on Anvil, verify reads that, uses Anvil — without you specifying anything.

The third rule means operators can configure a default deployment-wide network and never touch the `--network` flag in day-to-day use.

---

## Key Normalisation: The "base-sepolia" Problem

Network keys in JSON filenames use underscores (`base_sepolia.json`), but humans naturally type hyphens when they mean the same thing. The `normalize_network_key()` function maps both forms:

```python
normalize_network_key("base-sepolia")  # → "base_sepolia"
normalize_network_key("BASE_SEPOLIA")  # → "base_sepolia"
normalize_network_key("  Sepolia  ")   # → "sepolia"
```

This runs at every entry point — CLI arg, API form field, URL path parameter — so users can type either form and it just works.

---

## Backward Compatibility: The Empty-String Default

Adding two new fields to `EvidenceRecord` and `BatchEvidence` risked breaking every existing test and every evidence JSON file on disk. The solution: both fields default to `""` (empty string), and `from_dict()` uses `**{k: v for k, v in d.items() if k in fields}` to filter unknown keys.

Old evidence files load without touching the new fields. Old SQLite rows get `""` from `DEFAULT ''` column definitions. The `ensure_column()` migration pattern, already established in prior stages, extends cleanly:

```python
_NETWORK_COLUMNS = (
    ("network_key",        "TEXT DEFAULT ''"),
    ("explorer_base_url",  "TEXT DEFAULT ''"),
)
```

Run once per DB open, idempotent on existing columns. No migration scripts, no version tracking.

---

## The API Layer: Three New Endpoints

`GET /networks` lists all enabled configs. `GET /networks/current` returns what `DEFAULT_NETWORK` resolves to. `GET /networks/{key}` returns a single config or 404.

The 404 response uses the same JSON envelope as every other error in this system:

```json
{
  "status": "error",
  "message": "Unknown network: unknown_xyz. Available: anvil, base_sepolia, sepolia"
}
```

All existing register, verify, and batch endpoints gain a `network` form field that passes through the resolution chain.

---

## Dashboard: Injecting Network Context Everywhere

The cleanest dashboard change was in `_render()` — the single helper all routes call to build a Jinja2 response. Adding `_network_ctx()` there means every template gets:

```python
{
  "current_network_key":  "sepolia",
  "current_network_name": "Ethereum Sepolia",
  "current_chain_id":     11155111,
  "current_contract":     "0x...",
  "available_networks":   [...],
}
```

One change propagates the network badge to every page, and the network selector dropdowns in register/verify/batch forms populate from `available_networks` automatically.

---

## Test Coverage

145 new tests across two files:

- `proof_client/test_stage12_networks.py` (90 tests): Config loading, key normalisation, default resolution, env-var properties, explorer URL generation, schema fields, SQLite migration, batch evidence fields, proof JSON, CLI flag parsing, register integration, backward compatibility
- `api/test_stage12_networks_api.py` (55 tests): All three `/networks` endpoints, register/verify/batch with `network=` param, dashboard network selectors, OpenAPI path presence

All 90 prior-stage tests continue to pass (Stages 6–11).

---

## What's Next

Stage 13 will look at contract deployment automation — being able to deploy the PoE contract to a new network from the CLI itself, rather than requiring a separate Foundry workflow. Combined with Stage 12's config discovery, that should make spinning up a fresh network a single command.

The JSON-config-as-data pattern also opens an interesting door: network configs could be published to a registry or fetched from IPFS, making the supported network set dynamic rather than static. But that's a future conversation.

For now: the system speaks multiple chain dialects, the tests agree, and the old evidence records don't know anything changed.

---

*Code: github.com/Jeremy-Pei/blockchain-lab | Tag: v0.12.0*
