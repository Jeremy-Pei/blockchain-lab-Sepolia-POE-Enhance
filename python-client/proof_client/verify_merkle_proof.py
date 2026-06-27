"""
verify_merkle_proof.py — Verify that a file belongs to a registered Merkle batch

CLI:
  python -m proof_client.verify_merkle_proof --file <path> --proof <proof.json>
  python -m proof_client.verify_merkle_proof --file <path> --proof <proof.json> --chain

Exit codes:
  0  — all checks passed
  1  — verification failed (file tampered, proof invalid, or not on-chain)
  2  — usage / argument error
"""

import argparse
import json
import sys
from pathlib import Path

from proof_client.merkle_tree import sha256_file, verify_proof


# ── Core verification logic ───────────────────────────────────────


def verify_file_against_proof(
    file_path: Path,
    proof_json: dict,
) -> tuple[bool, dict]:
    """
    Verify a file's hash against a Merkle proof JSON (no chain call).

    Returns:
        (ok, details) where details contains all computed values and error messages.
    """
    details: dict = {}
    errors: list[str] = []

    # Step 1 — Recompute file SHA-256.
    if not file_path.exists():
        return False, {"error": f"File not found: {file_path}"}
    computed_hash = sha256_file(file_path)
    details["computed_file_hash"] = computed_hash

    # Step 2 — Compare with proof's file_hash.
    expected_hash = proof_json.get("file_hash", "")
    details["proof_file_hash"] = expected_hash
    if computed_hash.lower() != expected_hash.lower():
        errors.append(
            f"File hash mismatch: computed {computed_hash}, proof has {expected_hash}"
        )

    # Step 3 — Recompute Merkle root using the proof steps.
    merkle_root = proof_json.get("merkle_root", "")
    proof_steps = proof_json.get("proof", [])
    details["merkle_root"] = merkle_root

    proof_ok = verify_proof(computed_hash, proof_steps, merkle_root)
    details["proof_verification"] = "PASSED" if proof_ok else "FAILED"
    if not proof_ok:
        errors.append("Merkle proof verification failed (recomputed root does not match)")

    details["errors"] = errors
    ok = len(errors) == 0
    return ok, details


def verify_on_chain(merkle_root: str) -> tuple[bool, dict]:
    """
    Call contract.verify(merkle_root) and return (registered, info).
    """
    try:
        from proof_client.contract_client import verify_hash
        result = verify_hash(merkle_root)
        return result.get("registered", False), result
    except Exception as e:
        return False, {"error": str(e)}


# ── CLI ───────────────────────────────────────────────────────────


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify that a file belongs to a registered Merkle batch"
    )
    parser.add_argument("--file",  required=True, help="Path to the file to verify")
    parser.add_argument("--proof", required=True, help="Path to the .proof.json file")
    parser.add_argument("--chain", action="store_true",
                        help="Also verify the Merkle root is registered on-chain")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    file_path = Path(args.file)
    proof_path = Path(args.proof)

    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        return 2
    if not proof_path.exists():
        print(f"Error: proof file not found: {proof_path}", file=sys.stderr)
        return 2

    # Load proof JSON.
    try:
        proof_json = json.loads(proof_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading proof file: {e}", file=sys.stderr)
        return 2

    print(f"\nFile:  {file_path}")
    print(f"Proof: {proof_path}")
    print(f"Batch ID: {proof_json.get('batch_id', 'N/A')}")
    print()

    # Local verification.
    ok, details = verify_file_against_proof(file_path, proof_json)

    print(f"File hash (computed): {details.get('computed_file_hash', 'N/A')}")
    print(f"File hash (proof):    {details.get('proof_file_hash', 'N/A')}")
    print(f"Merkle root:          {details.get('merkle_root', 'N/A')}")
    print(f"Proof verification:   {details.get('proof_verification', 'N/A')}")

    # On-chain verification (optional).
    chain_ok = None
    if args.chain:
        merkle_root = proof_json.get("merkle_root", "")
        print("\nQuerying blockchain …")
        chain_ok, chain_info = verify_on_chain(merkle_root)
        if "error" in chain_info:
            print(f"Chain query error: {chain_info['error']}")
            chain_ok = False
        else:
            print(f"Blockchain root verification: {'PASSED' if chain_ok else 'FAILED'}")
            if chain_ok:
                print(f"Owner:     {chain_info.get('owner', 'N/A')}")
                print(f"Timestamp: {chain_info.get('timestamp', 'N/A')}")
                print(f"URI:       {chain_info.get('uri', 'N/A')}")

        tx = proof_json.get("transaction_hash", "")
        if tx:
            print(f"Transaction hash: {tx}")
        explorer = proof_json.get("explorer_url", "")
        if explorer:
            print(f"Explorer: {explorer}")

    # Final verdict.
    print()
    all_ok = ok and (chain_ok is not False)
    if all_ok:
        print("✅ VERIFICATION PASSED")
        if args.chain and chain_ok:
            print("   File belongs to registered batch (on-chain confirmed).")
        elif not args.chain:
            print("   File hash matches the proof. Run --chain to confirm on-chain.")
    else:
        print("❌ VERIFICATION FAILED")
        for err in details.get("errors", []):
            print(f"   • {err}")
        if args.chain and chain_ok is False:
            print("   • Merkle root is NOT registered on-chain (or query failed).")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
