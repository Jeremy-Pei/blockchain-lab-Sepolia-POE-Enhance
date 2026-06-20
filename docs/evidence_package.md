# Evidence Package Example

## File Information

- **File name:** `my_work.txt`
- **SHA-256 hash:** `0x9689583682fe9968981ebbc84e4067c0924baa56e8ed48a7286a2f4836d242fe`
- **URI:** `local://my_work.txt`

## Blockchain Information

- **Network:** Local Anvil Testnet (RPC: `http://127.0.0.1:8545`)
- **Contract address:** `0x5FbDB2315678afecb367f032d93F642f64180aa3`
- **Transaction hash:** `0xc4b67c5358f8a633d7983744fd50cb89ce18e146c08a2ad8eada762dc1203f36`
- **Block number:** `3`
- **Owner address:** `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`
- **Timestamp:** `1778997403` (UTC时间戳, 对应北京时间 2026-05-17 13:56:43)

## Verification Method

1. **Recalculate SHA-256 hash of the original file.**
   Ensure that the locally computed hash matches `0x9689583682fe9968981ebbc84e4067c0924baa56e8ed48a7286a2f4836d242fe`. If the file has been altered by even a single byte, the hashes will diverge.

2. **Query ProofOfExistence.verify(fileHash).**
   Using a blockchain explorer or an RPC script, query the `verify` function on the smart contract deployed at `0x5FbDB2315678afecb367f032d93F642f64180aa3` passing the recalculated hash.

3. **Compare returned owner, timestamp, and URI.**
   - The returned `owner` should match the registrant's address (`0xf39F...`).
   - The returned `timestamp` is the immutable block timestamp, proving the file existed at or before this exact moment.
   - The returned `URI` provides human-readable context or a locator (e.g., an IPFS CID or local path) related to the file's origin. 
   
If all outputs match this Evidence Package, mathematical proof of the file's integrity and temporal existence is firmly established.
