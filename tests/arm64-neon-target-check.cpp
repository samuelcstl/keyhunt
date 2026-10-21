/*
 * Independent bitmask oracle for the NEON final-HASH160 target comparer.
 * Uses the existing complete 4-lane RIPEMD digest path as an oracle:
 * exact target equals one/multiple lanes, nonmatching targets, varied input.
 */
#include "../hash/ripemd160.h"
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>

int main() {
    std::mt19937_64 rng(0x71a76b17ULL);
    alignas(16) uint8_t sha[4][32];
    uint8_t out[4][20];
    uint8_t target[20];
    constexpr int TRIALS = 4096;
    int checked=0;
    for (int n=0;n<TRIALS;n++) {
        for (auto &lane:sha)
            for (auto &b:lane)
                b=static_cast<uint8_t>(rng());
        // Also exercise exact 2+ matching lanes (not just one).
        if (n % 5 == 0)
            std::memcpy(sha[1],sha[0],32);
        if (n % 11 == 0) {
            std::memcpy(sha[2],sha[0],32);
            std::memcpy(sha[3],sha[0],32);
        }
        ripemd160sse_32(sha[0],sha[1],sha[2],sha[3],
                        out[0],out[1],out[2],out[3]);
        for (int candidate=0;candidate<5;candidate++) {
            if (candidate < 4)
                std::memcpy(target,out[candidate],20);
            else {
                std::memcpy(target,out[0],20);
                target[static_cast<unsigned>(n)%20] ^= 0x5au;
            }
            const uint8_t actual = ripemd160sse_32_target(
                sha[0],sha[1],sha[2],sha[3],target);
            unsigned expected=0;
            for (int lane=0;lane<4;lane++)
                if (!std::memcmp(out[lane],target,20))
                    expected|=1u<<lane;
            if (actual!=expected) {
                std::fprintf(stderr,
                    "mismatch batch=%d target_index=%d actual=0x%x expected=0x%x\n",
                    n,candidate,actual,expected);
                return 1;
            }
            ++checked;
        }
    }
    std::printf("PASS: %d exact NEON 4-lane target masks against full RIPEMD160 digests\n",
                checked);
    return 0;
}
