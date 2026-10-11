/*
 * ARMv8 SHA256 two-stream interleaved and hardware-scheduled adapter.
 * Inspired by samuelcstl/btc-sha256d-engine:
 * native/bounded/include/bounded/backends/arm_sha2_common.hpp
 *
 * Both streams are independent. Hardware SHA256SU0/SU1 perform the 16->64
 * message expansion; SHA256H/H2 do all 64 rounds. The two streams are
 * interleaved for dependency hiding. Works on one or two pre-padded SHA256
 * blocks, so compressed and uncompressed public-key encoding are supported.
 * Keyhunt's original scalar-RIPEMD and fixed-width ECC engine are unchanged.
 */
#include <arm_neon.h>
#include <cstdint>
#include "sha256.h"
#include "ripemd160.h"

#if !defined(__aarch64__) || !defined(__ARM_FEATURE_SHA2)
#error "ARMv8 SHA256 SU2 requires AArch64 SHA2 intrinsics"
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

inline void arm_compress_rounds_2way(
    uint32x4_t& state0_a,
    uint32x4_t& state1_a,
    uint32x4_t& state0_b,
    uint32x4_t& state1_b,
    uint32x4_t message_a[4],
    uint32x4_t message_b[4]
) {
    const uint32x4_t save0_a = state0_a;
    const uint32x4_t save1_a = state1_a;
    const uint32x4_t save0_b = state0_b;
    const uint32x4_t save1_b = state1_b;

    auto message0_a = message_a[0];
    auto message1_a = message_a[1];
    auto message2_a = message_a[2];
    auto message3_a = message_a[3];
    auto message0_b = message_b[0];
    auto message1_b = message_b[1];
    auto message2_b = message_b[2];
    auto message3_b = message_b[3];

#define PCA_INDEPENDENT_SCHEDULED_GROUP( \
    GROUP, CURRENT_A, NEXT1_A, NEXT2_A, NEXT3_A, \
    CURRENT_B, NEXT1_B, NEXT2_B, NEXT3_B \
) \
    do { \
        const auto constants_##GROUP = \
            vld1q_u32(K + 4 * (GROUP)); \
        const auto rounds_a_##GROUP = \
            vaddq_u32((CURRENT_A), constants_##GROUP); \
        const auto rounds_b_##GROUP = \
            vaddq_u32((CURRENT_B), constants_##GROUP); \
        const auto schedule_a_##GROUP = \
            vsha256su0q_u32((CURRENT_A), (NEXT1_A)); \
        const auto schedule_b_##GROUP = \
            vsha256su0q_u32((CURRENT_B), (NEXT1_B)); \
        const auto previous0_a_##GROUP = state0_a; \
        const auto previous0_b_##GROUP = state0_b; \
        state0_a = vsha256hq_u32(state0_a, state1_a, rounds_a_##GROUP); \
        state0_b = vsha256hq_u32(state0_b, state1_b, rounds_b_##GROUP); \
        state1_a = vsha256h2q_u32( \
            state1_a, previous0_a_##GROUP, rounds_a_##GROUP \
        ); \
        state1_b = vsha256h2q_u32( \
            state1_b, previous0_b_##GROUP, rounds_b_##GROUP \
        ); \
        (CURRENT_A) = vsha256su1q_u32( \
            schedule_a_##GROUP, (NEXT2_A), (NEXT3_A) \
        ); \
        (CURRENT_B) = vsha256su1q_u32( \
            schedule_b_##GROUP, (NEXT2_B), (NEXT3_B) \
        ); \
    } while (false)

#define PCA_INDEPENDENT_FINAL_GROUP(GROUP, CURRENT_A, CURRENT_B) \
    do { \
        const auto constants_##GROUP = \
            vld1q_u32(K + 4 * (GROUP)); \
        const auto rounds_a_##GROUP = \
            vaddq_u32((CURRENT_A), constants_##GROUP); \
        const auto rounds_b_##GROUP = \
            vaddq_u32((CURRENT_B), constants_##GROUP); \
        const auto previous0_a_##GROUP = state0_a; \
        const auto previous0_b_##GROUP = state0_b; \
        state0_a = vsha256hq_u32(state0_a, state1_a, rounds_a_##GROUP); \
        state0_b = vsha256hq_u32(state0_b, state1_b, rounds_b_##GROUP); \
        state1_a = vsha256h2q_u32( \
            state1_a, previous0_a_##GROUP, rounds_a_##GROUP \
        ); \
        state1_b = vsha256h2q_u32( \
            state1_b, previous0_b_##GROUP, rounds_b_##GROUP \
        ); \
    } while (false)

    PCA_INDEPENDENT_SCHEDULED_GROUP(
        0,
        message0_a, message1_a, message2_a, message3_a,
        message0_b, message1_b, message2_b, message3_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        1,
        message1_a, message2_a, message3_a, message0_a,
        message1_b, message2_b, message3_b, message0_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        2,
        message2_a, message3_a, message0_a, message1_a,
        message2_b, message3_b, message0_b, message1_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        3,
        message3_a, message0_a, message1_a, message2_a,
        message3_b, message0_b, message1_b, message2_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        4,
        message0_a, message1_a, message2_a, message3_a,
        message0_b, message1_b, message2_b, message3_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        5,
        message1_a, message2_a, message3_a, message0_a,
        message1_b, message2_b, message3_b, message0_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        6,
        message2_a, message3_a, message0_a, message1_a,
        message2_b, message3_b, message0_b, message1_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        7,
        message3_a, message0_a, message1_a, message2_a,
        message3_b, message0_b, message1_b, message2_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        8,
        message0_a, message1_a, message2_a, message3_a,
        message0_b, message1_b, message2_b, message3_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        9,
        message1_a, message2_a, message3_a, message0_a,
        message1_b, message2_b, message3_b, message0_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        10,
        message2_a, message3_a, message0_a, message1_a,
        message2_b, message3_b, message0_b, message1_b
    );
    PCA_INDEPENDENT_SCHEDULED_GROUP(
        11,
        message3_a, message0_a, message1_a, message2_a,
        message3_b, message0_b, message1_b, message2_b
    );
    PCA_INDEPENDENT_FINAL_GROUP(12, message0_a, message0_b);
    PCA_INDEPENDENT_FINAL_GROUP(13, message1_a, message1_b);
    PCA_INDEPENDENT_FINAL_GROUP(14, message2_a, message2_b);
    PCA_INDEPENDENT_FINAL_GROUP(15, message3_a, message3_b);

#undef PCA_INDEPENDENT_FINAL_GROUP
#undef PCA_INDEPENDENT_SCHEDULED_GROUP

    state0_a = vaddq_u32(state0_a, save0_a);
    state1_a = vaddq_u32(state1_a, save1_a);
    state0_b = vaddq_u32(state0_b, save0_b);
    state1_b = vaddq_u32(state1_b, save1_b);
}

inline void compress2(uint32_t a[8], uint32_t b[8],
                      const uint32_t *block_a, const uint32_t *block_b) {
    uint32x4_t state0_a = vld1q_u32(a);
    uint32x4_t state1_a = vld1q_u32(a + 4);
    uint32x4_t state0_b = vld1q_u32(b);
    uint32x4_t state1_b = vld1q_u32(b + 4);
    uint32x4_t words_a[4] = {
        vld1q_u32(block_a), vld1q_u32(block_a + 4),
        vld1q_u32(block_a + 8), vld1q_u32(block_a + 12)
    };
    uint32x4_t words_b[4] = {
        vld1q_u32(block_b), vld1q_u32(block_b + 4),
        vld1q_u32(block_b + 8), vld1q_u32(block_b + 12)
    };
    arm_compress_rounds_2way(state0_a, state1_a, state0_b, state1_b,
                              words_a, words_b);
    vst1q_u32(a, state0_a);
    vst1q_u32(a + 4, state1_a);
    vst1q_u32(b, state0_b);
    vst1q_u32(b + 4, state1_b);
}

inline void pack_digest(const uint32_t state[8], uint8_t *out) {
    for (unsigned j = 0; j < 8; j++) {
        out[4*j]   = static_cast<uint8_t>(state[j] >> 24);
        out[4*j+1] = static_cast<uint8_t>(state[j] >> 16);
        out[4*j+2] = static_cast<uint8_t>(state[j] >> 8);
        out[4*j+3] = static_cast<uint8_t>(state[j]);
    }
}

inline void sha256_pair(const uint32_t *a, const uint32_t *b,
                        unsigned blocks, uint8_t *da, uint8_t *db) {
    uint32_t state_a[8] = {
        0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
        0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u
    };
    uint32_t state_b[8] = {
        0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
        0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u
    };
    for (unsigned i=0; i < blocks; i++) {
        compress2(state_a, state_b, a + 16*i, b + 16*i);
    }
    pack_digest(state_a, da);
    pack_digest(state_b, db);
}
} // namespace

void sha256sse_1B(uint32_t *i0,uint32_t *i1,uint32_t *i2,uint32_t *i3,
                  uint8_t *d0,uint8_t *d1,uint8_t *d2,uint8_t *d3) {
    sha256_pair(i0,i1,1,d0,d1);
    sha256_pair(i2,i3,1,d2,d3);
}

void sha256sse_2B(uint32_t *i0,uint32_t *i1,uint32_t *i2,uint32_t *i3,
                  uint8_t *d0,uint8_t *d1,uint8_t *d2,uint8_t *d3) {
    sha256_pair(i0,i1,2,d0,d1);
    sha256_pair(i2,i3,2,d2,d3);
}
