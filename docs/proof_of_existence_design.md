# Proof of Existence Design

Goal:

Store a file hash on blockchain to prove that a specific version
of a file existed before a certain blockchain timestamp.

Basic flow:

1. Select a file.
2. Compute SHA-256 hash.
3. Submit hash to smart contract.
4. Save transaction hash, block number, contract address, and timestamp.
