#pragma once

#include <string>

struct Transaction {
    std::string sender;
    std::string receiver;
    double amount;
    std::string signature;
};
