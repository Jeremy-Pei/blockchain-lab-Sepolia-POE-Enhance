#pragma once

#include <string>
#include <vector>

struct Block {
    std::size_t index;
    std::string previous_hash;
    std::string merkle_root;
    std::string timestamp;
    std::size_t nonce;
    std::string hash;
};
