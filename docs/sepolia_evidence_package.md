# Sepolia Evidence Package

## File Information

- File name: sepolia_work.txt
- SHA-256 hash:
- URI: sepolia://sepolia_work.txt

## Blockchain Information

- Network: Ethereum Sepolia
- Contract address:
- Register transaction hash:
- Block number:
- Gas used:
- Owner address:

## Explorer

- Sepolia Etherscan search keyword:
  - transaction hash
  - contract address

## Verification Logic

1. Recalculate the SHA-256 hash of the file.
2. Query `verify(fileHash)` from the Sepolia contract.
3. If owner and timestamp are returned, the file version has been registered.
4. If timestamp is zero, the file version is not registered.