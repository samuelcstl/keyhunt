/*
 * Dedicated ARMv8 SHA2 backend for Keyhunt's four-message hashing API.
 * The KEYBUFF* macros already construct SHA256-padded, big-endian 32-bit
 * message words. Feed those words directly into the SHA256 hardware rounds.
 *
 * This deliberately uses SHA256H/H2 intrinsics, rather than asking OpenSSL's
 * generic hashing API to choose an implementation on our behalf. RIPEMD160
 * remains scalar here, giving us an isolated SHA2 acceleration experiment.
 *
 * Requires a CPU with FEAT_SHA256 (Linux /proc/cpuinfo 'sha2').
 */
#include <arm_neon.h>
#include <cstdint>
#include "sha256.h"
#include "ripemd160.h"

#if !defined(__aarch64__) || !defined(__ARM_FEATURE_SHA2)
#error "Build this SHA2 adapter on AArch64 with -march=armv8.2-a+sha2"
#endif

namespace {

alignas(16) constexpr uint32_t K[64] = {
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,
  0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,
  0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,
  0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,
  0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,
  0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,
  0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,
  0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,
  0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
};

static inline uint32_t rotr(uint32_t x, unsigned int n) {
  return (x >> n) | (x << (32 - n));
}

static inline void compress(uint32_t state[8], const uint32_t block[16]) {
  // The calling KEYBUFF* macros have already laid out and padded 1 or 2
  // blocks of big-endian SHA256 message words in host-endian uint32_t slots.
  alignas(16) uint32_t w[64];
  for (int t = 0; t < 16; ++t) w[t] = block[t];
  for (int t = 16; t < 64; ++t) {
    uint32_t s0 = rotr(w[t-15], 7) ^ rotr(w[t-15], 18) ^ (w[t-15] >> 3);
    uint32_t s1 = rotr(w[t-2], 17) ^ rotr(w[t-2], 19) ^ (w[t-2] >> 10);
    w[t] = w[t-16] + s0 + w[t-7] + s1;
  }

  uint32x4_t abcd = vld1q_u32(state);
  uint32x4_t efgh = vld1q_u32(state + 4);
  const uint32x4_t old_abcd = abcd;
  const uint32x4_t old_efgh = efgh;

  for (int t = 0; t < 64; t += 4) {
    const uint32x4_t wk =
      vaddq_u32(vld1q_u32(w + t), vld1q_u32(K + t));
    const uint32x4_t before = abcd;
    abcd = vsha256hq_u32(abcd, efgh, wk);
    efgh = vsha256h2q_u32(efgh, before, wk);
  }
  vst1q_u32(state, vaddq_u32(abcd, old_abcd));
  vst1q_u32(state + 4, vaddq_u32(efgh, old_efgh));
}

static inline void sha2_padded(const uint32_t *blocks, unsigned num_blocks,
                               uint8_t digest[32]) {
  uint32_t state[8] = {
    0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
    0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19
  };
  for (unsigned i = 0; i < num_blocks; ++i)
    compress(state, blocks + 16 * i);
  for (unsigned i = 0; i < 8; ++i) {
    const uint32_t x = state[i];
    digest[4*i+0] = static_cast<uint8_t>(x >> 24);
    digest[4*i+1] = static_cast<uint8_t>(x >> 16);
    digest[4*i+2] = static_cast<uint8_t>(x >> 8);
    digest[4*i+3] = static_cast<uint8_t>(x);
  }
}

static inline void four(const uint32_t *i0, const uint32_t *i1,
                        const uint32_t *i2, const uint32_t *i3,
                        uint8_t *d0, uint8_t *d1, uint8_t *d2, uint8_t *d3,
                        unsigned blocks) {
  sha2_padded(i0, blocks, d0);
  sha2_padded(i1, blocks, d1);
  sha2_padded(i2, blocks, d2);
  sha2_padded(i3, blocks, d3);
}
} // namespace

void sha256sse_1B(uint32_t *i0, uint32_t *i1, uint32_t *i2, uint32_t *i3,
                  uint8_t *d0, uint8_t *d1, uint8_t *d2, uint8_t *d3) {
  four(i0, i1, i2, i3, d0, d1, d2, d3, 1);
}

void sha256sse_2B(uint32_t *i0, uint32_t *i1, uint32_t *i2, uint32_t *i3,
                  uint8_t *d0, uint8_t *d1, uint8_t *d2, uint8_t *d3) {
  four(i0, i1, i2, i3, d0, d1, d2, d3, 2);
}

#ifndef KEYHUNT_NEON_RIPEMD160
void ripemd160sse_32(uint8_t *i0, uint8_t *i1, uint8_t *i2, uint8_t *i3,
                      uint8_t *d0, uint8_t *d1, uint8_t *d2, uint8_t *d3) {
  ripemd160(i0, 32, d0);
  ripemd160(i1, 32, d1);
  ripemd160(i2, 32, d2);
  ripemd160(i3, 32, d3);
}
#endif // KEYHUNT_NEON_RIPEMD160
