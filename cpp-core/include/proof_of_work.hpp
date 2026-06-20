#pragma once

#include <string>

class ProofOfWork {
public:
    static bool is_valid_hash(const std::string& hash, int difficulty);
};
