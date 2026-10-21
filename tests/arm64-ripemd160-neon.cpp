/*
 * Independent regression vectors for the four-lane NEON RIPEMD-160 backend.
 * Known answer computed by libcrypto only in this test; the engine itself
 * has no dependency on libcrypto.
 */
#include <openssl/ripemd.h>
#include <cstdint>
#include <cstdio>
#include <cstring>

extern void ripemd160sse_32(uint8_t*,uint8_t*,uint8_t*,uint8_t*,
                            uint8_t*,uint8_t*,uint8_t*,uint8_t*);

static uint64_t state=0x7a55e2c451fed239ULL;
static uint64_t next() {
  state ^= state<<13;
  state ^= state>>7;
  state ^= state<<17;
  return state;
}

int main() {
  alignas(16) uint8_t in[4][64] = {};
  uint8_t original[4][32], expected[4][20], actual[4][20];
  constexpr int iterations=2048;
  for (int iter=0;iter<iterations;iter++) {
    for (int lane=0;lane<4;lane++) {
      for (int i=0;i<32;i++) {
        if (iter==0) in[lane][i]=0;
        else if (iter==1) in[lane][i]=0xff;
        else if (iter==2) in[lane][i]=static_cast<uint8_t>(lane*32+i);
        else in[lane][i]=static_cast<uint8_t>(next() >> 16);
      }
      std::memcpy(original[lane],in[lane],32);
      RIPEMD160(in[lane],32,expected[lane]);
    }
    ripemd160sse_32(in[0],in[1],in[2],in[3],
                     actual[0],actual[1],actual[2],actual[3]);
    for (int lane=0;lane<4;lane++) {
      if (std::memcmp(expected[lane],actual[lane],20)!=0) {
        std::fprintf(stderr,"FAIL: iter=%d lane=%d digest mismatch\n",iter,lane);
        return 1;
      }
      if (std::memcmp(original[lane],in[lane],32)!=0) {
        std::fprintf(stderr,"FAIL: iter=%d lane=%d input modified\n",iter,lane);
        return 1;
      }
    }
  }
  std::printf("PASS: %d independent 4-lane RIPEMD160 batches (%d digests)\n",
              iterations,iterations*4);
  return 0;
}
