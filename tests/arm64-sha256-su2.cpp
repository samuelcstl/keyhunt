/*
 * Independent SHA256 digest regression for the 2-stream SU0/SU1 engine.
 * The engine consumes Keyhunt's already-padded big-endian 32-bit words.
 * Compare 4 independent digests per call to OpenSSL's complete SHA256.
 */
#include <openssl/sha.h>
#include <cstdint>
#include <cstdio>
#include <cstring>

extern void sha256sse_1B(uint32_t*,uint32_t*,uint32_t*,uint32_t*,
                         uint8_t*,uint8_t*,uint8_t*,uint8_t*);
extern void sha256sse_2B(uint32_t*,uint32_t*,uint32_t*,uint32_t*,
                         uint8_t*,uint8_t*,uint8_t*,uint8_t*);

static uint64_t state = 0x12345afedcba9961ULL;
static uint64_t rng() {
    state ^= state << 13;
    state ^= state >> 7;
    state ^= state << 17;
    return state;
}

static void prepare(const uint8_t *msg, unsigned len,
                    uint32_t words[32]) {
    uint8_t block[128]={};
    std::memcpy(block,msg,len);
    block[len] = 0x80;
    const unsigned blocks = len == 33 ? 1 : 2;
    const uint64_t bitlen = uint64_t(len)*8;
    for (unsigned i=0;i<8;i++)
        block[64*blocks - 1 - i] = uint8_t(bitlen >> (8*i));
    for (unsigned i=0;i<16*blocks;i++) {
        words[i] = (uint32_t(block[4*i]) << 24)
                 | (uint32_t(block[4*i+1]) << 16)
                 | (uint32_t(block[4*i+2]) << 8)
                 | (uint32_t(block[4*i+3]));
    }
}

int main() {
    alignas(16) uint32_t padded[4][32];
    uint8_t input[4][65];
    uint8_t expected[4][32],actual[4][32];
    constexpr int batches = 2048;
    for (int iter=0;iter<batches;iter++) {
        const unsigned len = (iter & 1) ? 65 : 33;
        for (int lane=0;lane<4;lane++) {
            for (unsigned i=0;i<len;i++) {
                input[lane][i] = iter == 0 ? 0
                    : iter == 1 ? 255
                    : iter == 2 ? static_cast<uint8_t>(lane+i)
                    : static_cast<uint8_t>(rng() >> 16);
            }
            SHA256(input[lane],len,expected[lane]);
            prepare(input[lane],len,padded[lane]);
        }
        if (len == 33)
            sha256sse_1B(padded[0],padded[1],padded[2],padded[3],
                          actual[0],actual[1],actual[2],actual[3]);
        else
            sha256sse_2B(padded[0],padded[1],padded[2],padded[3],
                          actual[0],actual[1],actual[2],actual[3]);
        for (int lane=0;lane<4;lane++) {
            if (std::memcmp(expected[lane],actual[lane],32)) {
                std::fprintf(stderr,
                    "FAIL: SHA256 SU2 digest mismatch at batch %d, lane %d, len %u\n",
                    iter,lane,len);
                return 1;
            }
        }
    }
    std::printf("PASS: SHA256 SU2 %d cross-checked digests (33 and 65 bytes)\n",
                4*batches);
    return 0;
}
