"""
report_template.py — Unified evidence certificate content structure

Single source of truth for what goes into both Markdown and PDF
evidence certificates. pdf_report.py and generate_report.py both
draw from this module.
"""

from datetime import datetime, timezone
from proof_client.evidence_schema import EvidenceRecord


LIMITATIONS_TEXT = (
    "This certificate provides technical evidence that the SHA-256 hash "
    "of a file was registered on the specified blockchain network at or "
    "before the recorded block timestamp. It does not, by itself, prove "
    "legal authorship or replace copyright registration, notarization, "
    "or professional legal procedures."
)

DECLARATION_TEXT = (
    "The information in this certificate was generated automatically by "
    "proof_client based on on-chain data. The blockchain record is immutable "
    "and can be independently verified by anyone with access to a compatible "
    "Ethereum JSON-RPC node."
)


def build_certificate_data(record: EvidenceRecord, manifest_hash: str = "") -> dict:
    """
    Return a structured dict of all certificate fields.

    Args:
        record: EvidenceRecord to summarise.
        manifest_hash: Optional SHA-256 of the package manifest.json.

    Returns:
        Dict with one key per certificate field.
    """
    short = record.file_hash.replace("0x", "")[:8]
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    tx = record.tx_hash
    if tx and not tx.startswith("0x"):
        tx = f"0x{tx}"

    return {
        # ── Summary ──────────────────────────────────────────────────
        "certificate_id": f"POE-{short.upper()}",
        "generated_at_utc": now_utc,
        # ── Work Information ─────────────────────────────────────────
        "file_name": record.file_name,
        "file_hash": record.file_hash,
        "uri": record.uri,
        # ── Blockchain Registration ──────────────────────────────────
        "owner_address": record.owner or "N/A",
        "contract_address": record.contract_address or "N/A",
        "network": record.network,
        "chain_id": record.chain_id,
        "tx_hash": tx or "N/A",
        "block_number": record.block_number,
        "block_timestamp": record.timestamp_utc,
        "explorer_url": record.explorer_link or "N/A",
        # ── Off-Chain Storage (IPFS, Stage 7) ────────────────────────
        "has_ipfs": record.has_ipfs,
        "ipfs_cid": record.ipfs_cid or "Not available",
        "ipfs_uri": record.ipfs_uri or "Not available",
        "ipfs_gateway_url": record.ipfs_gateway_url or "Not available",
        "ipfs_provider": record.ipfs_provider or "Not available",
        "ipfs_uploaded_at": record.ipfs_uploaded_at or "Not available",
        # ── Local Evidence ───────────────────────────────────────────
        "evidence_filename": f"evidence_{short}.json",
        "package_manifest_hash": manifest_hash or "N/A",
        # ── Boilerplate ──────────────────────────────────────────────
        "limitations": LIMITATIONS_TEXT,
        "declaration": DECLARATION_TEXT,
    }


def build_markdown_certificate(record: EvidenceRecord, manifest_hash: str = "") -> str:
    """Return a fully-formatted Markdown evidence certificate string."""
    d = build_certificate_data(record, manifest_hash)

    return f"""# Proof of Existence Evidence Certificate

**Certificate ID:** {d['certificate_id']}
**Generated at UTC:** {d['generated_at_utc']}

---

## 1. Certificate Summary

This certificate confirms that the SHA-256 fingerprint of the work described
below was registered on the {d['network']} blockchain.

---

## 2. Work Information

| Field | Value |
|-------|-------|
| **File name** | `{d['file_name']}` |
| **SHA-256 hash** | `{d['file_hash']}` |
| **URI** | `{d['uri']}` |

---

## 3. File Fingerprint

```
{d['file_hash']}
```

To recompute and verify:
```bash
shasum -a 256 "{d['file_name']}"
```

---

## 4. Blockchain Registration

| Field | Value |
|-------|-------|
| **Owner address** | `{d['owner_address']}` |
| **Contract address** | `{d['contract_address']}` |
| **Network** | {d['network']} |
| **Chain ID** | {d['chain_id']} |
| **Transaction hash** | `{d['tx_hash']}` |
| **Block number** | {d['block_number']} |
| **Block timestamp** | {d['block_timestamp']} |
| **Explorer URL** | {d['explorer_url']} |

---

## 5. Off-Chain Storage (IPFS)

The SHA-256 hash above proves *which file version* was registered. The IPFS
CID below identifies a *retrievable copy of the content* in the IPFS network.
They are derived from the same bytes but are not the same identifier.

| Field | Value |
|-------|-------|
| **IPFS CID** | `{d['ipfs_cid']}` |
| **IPFS URI** | `{d['ipfs_uri']}` |
| **Gateway URL** | {d['ipfs_gateway_url']} |
| **Provider** | {d['ipfs_provider']} |
| **Uploaded at (UTC)** | {d['ipfs_uploaded_at']} |

---

## 6. Local Evidence Record

| Field | Value |
|-------|-------|
| **Evidence JSON** | `{d['evidence_filename']}` |
| **Package manifest hash** | `{d['package_manifest_hash']}` |

---

## 7. Verification Method

**Step 1 — Verify the file fingerprint**

```bash
shasum -a 256 "original/{d['file_name']}"
```
The output must match: `{d['file_hash']}`

**Step 2 — Query the blockchain**

Call `verify(fileHash)` on the smart contract:
- Contract: `{d['contract_address']}`
- Argument: `{d['file_hash']}`
- Expected owner: `{d['owner_address']}`

**Step 3 — Verify the evidence package**

```bash
python -m proof_client.verify_package <path_to_package.zip>
```

**Step 4 — Verify the IPFS content (if a CID is present)**

```bash
python -m proof_client.verify_ipfs --hash {d['file_hash']}
```
This downloads the file from IPFS, recomputes its SHA-256, and confirms it
matches the fingerprint above.

---

## 8. Limitations

> {d['limitations']}

---

## 9. Declaration

{d['declaration']}

---

*Certificate generated by proof\\_client · {d['generated_at_utc']}*
"""
