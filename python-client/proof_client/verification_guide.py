"""
verification_guide.py — Auto-generate third-party verification instructions

Produces two files inside a package's verification/ subdirectory:
  - verification_guide.md   : human-readable step-by-step guide
  - verification_commands.txt : copy-pasteable shell commands
"""

from pathlib import Path

from proof_client.evidence_schema import EvidenceRecord


def _ipfs_section(record: EvidenceRecord) -> str:
    """Return the Step 4 IPFS verification section (Markdown)."""
    if not record.has_ipfs:
        return """## Step 4 — Verify the IPFS Content

No IPFS content identifier (CID) was recorded for this file, so this step is
not applicable. The proof above relies on the on-chain hash and the local
evidence package only.

---
"""

    gw = record.ipfs_gateway_url or f"https://ipfs.io/ipfs/{record.ipfs_cid}"
    return f"""## Step 4 — Verify the IPFS Content

A copy of the file is stored on IPFS under a content identifier (CID).
Download it from any gateway, recompute its SHA-256, and confirm it matches
the fingerprint registered on-chain.

- **IPFS CID:** `{record.ipfs_cid}`
- **IPFS URI:** `{record.ipfs_uri}`
- **Gateway URL:** {gw}
- **Provider:** {record.ipfs_provider or 'N/A'}

```bash
# Download the file from the IPFS gateway
curl -L "{gw}" -o ipfs_downloaded_file

# Recompute its SHA-256 and compare with the registered hash
shasum -a 256 ipfs_downloaded_file
# Expected: {record.file_hash}
```

Or use this client:
```bash
python -m proof_client.verify_ipfs --cid {record.ipfs_cid} --expected-hash {record.file_hash}
```

> **Note:** The SHA-256 hash proves the file version in this system. The IPFS
> CID identifies the content in the IPFS network. They are related but not
> identical — the SHA-256 remains the primary evidence hash.

---
"""


def build_verification_guide(record: EvidenceRecord) -> str:
    """Return the full text of the verification guide (Markdown)."""
    tx = record.tx_hash
    if tx and not tx.startswith("0x"):
        tx = f"0x{tx}"

    return f"""# Third-Party Verification Guide

This guide explains how an independent party can verify the proof of
existence certificate WITHOUT relying on this software or the issuer.

---

## What Is Being Verified?

- **File:** `{record.file_name}`
- **SHA-256 hash:** `{record.file_hash}`
- **Blockchain:** {record.network} (Chain ID {record.chain_id})
- **Contract:** `{record.contract_address}`
- **Transaction:** `{tx}`
- **Block:** {record.block_number}
- **Block timestamp:** {record.timestamp_utc}

---

## Step 1 — Verify the File Fingerprint

Recompute the SHA-256 hash of the original file and compare it to
the value recorded on the blockchain.

**On macOS / Linux:**
```bash
shasum -a 256 original/{record.file_name}
```

**On Windows (PowerShell):**
```powershell
Get-FileHash original\\{record.file_name} -Algorithm SHA256
```

**Expected output:** `{record.file_hash}`

If the hash matches, the file has not been modified since registration.

---

## Step 2 — Query the Blockchain

### Option A — Block Explorer (no software needed)

1. Open: {record.explorer_link or 'https://sepolia.etherscan.io'}
2. Look up transaction: `{tx}`
3. Confirm the transaction interacts with contract `{record.contract_address}`
4. Verify the block timestamp matches `{record.timestamp_utc}`

### Option B — Python / web3.py

```python
from web3 import Web3

w3 = Web3(Web3.HTTPProvider("YOUR_RPC_URL"))
contract = w3.eth.contract(
    address="{record.contract_address}",
    abi=[{{
        "name": "verify",
        "type": "function",
        "inputs": [{{"name": "fileHash", "type": "bytes32"}}],
        "outputs": [
            {{"name": "owner",     "type": "address"}},
            {{"name": "timestamp", "type": "uint256"}},
            {{"name": "uri",       "type": "string"}},
        ],
        "stateMutability": "view",
    }}],
)
file_hash_bytes = bytes.fromhex("{record.file_hash.replace('0x', '')}")
owner, timestamp, uri = contract.functions.verify(file_hash_bytes).call()
print("Owner:    ", owner)
print("Timestamp:", timestamp)
print("URI:      ", uri)
```

**Expected results:**
- `owner`     → `{record.owner or 'N/A'}`
- `timestamp` → `{record.timestamp}` ({record.timestamp_utc})
- `uri`       → `{record.uri}`

### Option C — ethers.js (Node.js)

```javascript
const {{ ethers }} = require("ethers");
const provider = new ethers.JsonRpcProvider("YOUR_RPC_URL");
const abi = ["function verify(bytes32) view returns (address, uint256, string)"];
const contract = new ethers.Contract("{record.contract_address}", abi, provider);
const [owner, timestamp, uri] = await contract.verify("{record.file_hash}");
console.log("Owner:", owner, "Timestamp:", timestamp.toString(), "URI:", uri);
```

---

## Step 3 — Verify the Evidence Package Integrity

```bash
python -m proof_client.verify_package <path_to_package.zip>
```

Or manually check SHA-256 of each file against `manifest.json`.

---

{_ipfs_section(record)}
## What This Proves

If all checks pass:
1. The file existed with its exact content on or before block {record.block_number}.
2. The registration was made by address `{record.owner or 'N/A'}`.
3. The evidence package has not been tampered with since generation.

## What This Does Not Prove

- Legal authorship or copyright ownership.
- That the registrant is the original creator of the work.
- Anything that requires notarization or legal proceedings.

---

*Generated by proof_client*
"""


def build_verification_commands(record: EvidenceRecord) -> str:
    """Return a plain-text file of copy-pasteable verification commands."""
    tx = record.tx_hash
    if tx and not tx.startswith("0x"):
        tx = f"0x{tx}"

    if record.has_ipfs:
        gw = record.ipfs_gateway_url or f"https://ipfs.io/ipfs/{record.ipfs_cid}"
        ipfs_block = f"""
# 6. Verify the IPFS content (CID: {record.ipfs_cid})
curl -L "{gw}" -o ipfs_downloaded_file
shasum -a 256 ipfs_downloaded_file
# Expected: {record.file_hash}
python -m proof_client.verify_ipfs --cid {record.ipfs_cid} --expected-hash {record.file_hash}
"""
    else:
        ipfs_block = "\n# 6. IPFS verification: no CID recorded for this file.\n"

    return f"""# Verification Commands
# File: {record.file_name}
# Hash: {record.file_hash}

# 1. Verify file fingerprint (macOS / Linux)
shasum -a 256 original/{record.file_name}
# Expected: {record.file_hash}

# 2. Verify file fingerprint (Windows PowerShell)
# Get-FileHash original\\{record.file_name} -Algorithm SHA256

# 3. Query blockchain (Python)
python3 -c "
from web3 import Web3
w3 = Web3(Web3.HTTPProvider('YOUR_RPC_URL'))
result = w3.eth.call({{
    'to': '{record.contract_address}',
    'data': w3.keccak(text='verify(bytes32)')[:4].hex() + '{record.file_hash.replace('0x', '')}'
}})
print(result)
"

# 4. Verify evidence package integrity
python -m proof_client.verify_package <path_to_package.zip>

# 5. View transaction on block explorer
# {record.explorer_link or 'N/A'}
{ipfs_block}

# Contract: {record.contract_address}
# Transaction: {tx}
# Block: {record.block_number}
# Timestamp: {record.timestamp_utc}
# Owner: {record.owner or 'N/A'}
"""


def write_verification_guide(record: EvidenceRecord, verification_dir: Path) -> tuple[Path, Path]:
    """
    Write verification_guide.md and verification_commands.txt to verification_dir.

    Returns:
        (guide_path, commands_path)
    """
    verification_dir.mkdir(parents=True, exist_ok=True)

    guide_path = verification_dir / "verification_guide.md"
    guide_path.write_text(build_verification_guide(record), encoding="utf-8")

    commands_path = verification_dir / "verification_commands.txt"
    commands_path.write_text(build_verification_commands(record), encoding="utf-8")

    return guide_path, commands_path
