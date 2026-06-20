// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract ProofOfExistence {
    struct Record {
        address owner;
        uint256 timestamp;
        string uri;
    }

    mapping(bytes32 => Record) private records;

    event Registered(
        bytes32 indexed fileHash,
        address indexed owner,
        uint256 timestamp,
        string uri
    );

    function register(bytes32 fileHash, string calldata uri) external {
        require(records[fileHash].timestamp == 0, "Already registered");

        records[fileHash] = Record({
            owner: msg.sender,
            timestamp: block.timestamp,
            uri: uri
        });

        emit Registered(fileHash, msg.sender, block.timestamp, uri);
    }

    function verify(bytes32 fileHash)
        external
        view
        returns (address owner, uint256 timestamp, string memory uri)
    {
        Record memory r = records[fileHash];
        return (r.owner, r.timestamp, r.uri);
    }
}
