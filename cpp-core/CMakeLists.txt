cmake_minimum_required(VERSION 3.20)

project(cpp_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(include)

add_executable(blockchain_core
    src/main.cpp
)
