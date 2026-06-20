#pragma once

#include <string>
#include <vector>

class MerkleTree {
public:
    static std::string build_root(const std::vector<std::string>& hashes);
};
