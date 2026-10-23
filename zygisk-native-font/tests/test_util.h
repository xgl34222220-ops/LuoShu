#pragma once

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

static int g_failures = 0;

#define CHECK(cond)                                                                 \
    do {                                                                            \
        if (!(cond)) {                                                              \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            ++g_failures;                                                           \
        }                                                                           \
    } while (0)

inline bool readBytes(const std::string &path, std::vector<unsigned char> *out) {
    FILE *f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    std::fseek(f, 0, SEEK_END);
    long n = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    out->resize(n > 0 ? size_t(n) : 0);
    size_t got = n > 0 ? std::fread(out->data(), 1, out->size(), f) : 0;
    std::fclose(f);
    return got == out->size();
}
