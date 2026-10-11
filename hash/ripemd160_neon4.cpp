/*
 * Four-lane, fixed-32-byte RIPEMD-160 for ARM NEON (AArch64 / Cortex-A76).
 *
 * This implements the complete standard 80-step dual-line compression for
 * four independent messages packed into four 32-bit NEON lanes. The message
 * layout is fixed:
 *   words 0..7 = SHA256 digest (little-endian RIPEMD160 message words);
 *   word 8 = 0x00000080; words 9..13 and 15 = 0; word 14 = 256 bits.
 *
 * Round scheduling is kept identical to the upstream Keyhunt SSE2 backend
 * (hash/ripemd160_sse.cpp); all rotates have immediate counts. Inputs are
 * unchanged, and outputs are the complete 20-byte digest for each lane.
 *
 * We deliberately retain the original SHA256H/H2 adapter unchanged in the
 * SHA2+NEON experiment. No hand-rolled cryptographic shortcut is involved.
 */
#include <arm_neon.h>
#include <cstdint>
#include <cstring>
#include "ripemd160.h"

#if !defined(__aarch64__)
#error "NEON RIPEMD160 backend requires AArch64"
#endif
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "This fixed-layout NEON RIPEMD160 implementation requires little-endian AArch64"
#endif

namespace {

using V = uint32x4_t;

// NEON 128-bit vectors: one independent digest per 32-bit lane.
#define ROL(x,n) vorrq_u32(vshlq_n_u32((x),(n)),vshrq_n_u32((x),32-(n)))
#define f1(x,y,z) veorq_u32((x),veorq_u32((y),(z)))
#define f2(x,y,z) vorrq_u32(vandq_u32((x),(y)),vbicq_u32((z),(x)))
#define f3(x,y,z) veorq_u32(vorrq_u32((x),vmvnq_u32((y))),(z))
#define f4(x,y,z) vorrq_u32(vandq_u32((x),(z)),vbicq_u32((y),(z)))
#define f5(x,y,z) veorq_u32((x),vorrq_u32((y),vmvnq_u32((z))))

#define ROUND(a,b,c,d,e,f,x,k,r) do { \
  const V u = vaddq_u32(vaddq_u32((a),(f)), \
                       vaddq_u32((x),vdupq_n_u32((k)))); \
  (a) = vaddq_u32(ROL(u,r),(e)); \
  (c) = ROL((c),10); \
} while (0)

#define R11(a,b,c,d,e,x,r) ROUND(a,b,c,d,e,f1(b,c,d),x,0,r)
#define R21(a,b,c,d,e,x,r) ROUND(a,b,c,d,e,f2(b,c,d),x,0x5A827999u,r)
#define R31(a,b,c,d,e,x,r) ROUND(a,b,c,d,e,f3(b,c,d),x,0x6ED9EBA1u,r)
#define R41(a,b,c,d,e,x,r) ROUND(a,b,c,d,e,f4(b,c,d),x,0x8F1BBCDCu,r)
#define R51(a,b,c,d,e,x,r) ROUND(a,b,c,d,e,f5(b,c,d),x,0xA953FD4Eu,r)
#define R12(a,b,c,d,e,x,r) ROUND(a,b,c,d,e,f5(b,c,d),x,0x50A28BE6u,r)
#define R22(a,b,c,d,e,x,r) ROUND(a,b,c,d,e,f4(b,c,d),x,0x5C4DD124u,r)
#define R32(a,b,c,d,e,x,r) ROUND(a,b,c,d,e,f3(b,c,d),x,0x6D703EF3u,r)
#define R42(a,b,c,d,e,x,r) ROUND(a,b,c,d,e,f2(b,c,d),x,0x7A6D76E9u,r)
#define R52(a,b,c,d,e,x,r) ROUND(a,b,c,d,e,f1(b,c,d),x,0,r)

// Read 32-bit SHA256 digest words without unaligned type-punning. All lane
// offsets are compile-time small constants after GCC unrolls the 8-word loop.
static inline V gather32(const uint8_t *p0, const uint8_t *p1,
                         const uint8_t *p2, const uint8_t *p3, int index) {
  uint32_t lane[4];
  std::memcpy(&lane[0],p0+4*index,4);
  std::memcpy(&lane[1],p1+4*index,4);
  std::memcpy(&lane[2],p2+4*index,4);
  std::memcpy(&lane[3],p3+4*index,4);
  return vld1q_u32(lane);
}

static inline void transform4(const uint8_t *p0, const uint8_t *p1,
                              const uint8_t *p2, const uint8_t *p3,
                              uint8_t *dst0, uint8_t *dst1,
                              uint8_t *dst2, uint8_t *dst3) {
  V w[16];
  for (int i=0;i<8;i++) w[i]=gather32(p0,p1,p2,p3,i);
  w[8]=vdupq_n_u32(0x80u);
  for (int i=9;i<14;i++) w[i]=vdupq_n_u32(0);
  w[14]=vdupq_n_u32(256u);
  w[15]=vdupq_n_u32(0);

  const V h0=vdupq_n_u32(0x67452301u);
  const V h1=vdupq_n_u32(0xEFCDAB89u);
  const V h2=vdupq_n_u32(0x98BADCFEu);
  const V h3=vdupq_n_u32(0x10325476u);
  const V h4=vdupq_n_u32(0xC3D2E1F0u);
  V a1=h0,b1=h1,c1=h2,d1=h3,e1=h4;
  V a2=h0,b2=h1,c2=h2,d2=h3,e2=h4;

  // Both 80-step lines, interleaved exactly as upstream's SSE2 backend.
    R11(a1, b1, c1, d1, e1, w[0], 11);
    R12(a2, b2, c2, d2, e2, w[5], 8);
    R11(e1, a1, b1, c1, d1, w[1], 14);
    R12(e2, a2, b2, c2, d2, w[14], 9);
    R11(d1, e1, a1, b1, c1, w[2], 15);
    R12(d2, e2, a2, b2, c2, w[7], 9);
    R11(c1, d1, e1, a1, b1, w[3], 12);
    R12(c2, d2, e2, a2, b2, w[0], 11);
    R11(b1, c1, d1, e1, a1, w[4], 5);
    R12(b2, c2, d2, e2, a2, w[9], 13);
    R11(a1, b1, c1, d1, e1, w[5], 8);
    R12(a2, b2, c2, d2, e2, w[2], 15);
    R11(e1, a1, b1, c1, d1, w[6], 7);
    R12(e2, a2, b2, c2, d2, w[11], 15);
    R11(d1, e1, a1, b1, c1, w[7], 9);
    R12(d2, e2, a2, b2, c2, w[4], 5);
    R11(c1, d1, e1, a1, b1, w[8], 11);
    R12(c2, d2, e2, a2, b2, w[13], 7);
    R11(b1, c1, d1, e1, a1, w[9], 13);
    R12(b2, c2, d2, e2, a2, w[6], 7);
    R11(a1, b1, c1, d1, e1, w[10], 14);
    R12(a2, b2, c2, d2, e2, w[15], 8);
    R11(e1, a1, b1, c1, d1, w[11], 15);
    R12(e2, a2, b2, c2, d2, w[8], 11);
    R11(d1, e1, a1, b1, c1, w[12], 6);
    R12(d2, e2, a2, b2, c2, w[1], 14);
    R11(c1, d1, e1, a1, b1, w[13], 7);
    R12(c2, d2, e2, a2, b2, w[10], 14);
    R11(b1, c1, d1, e1, a1, w[14], 9);
    R12(b2, c2, d2, e2, a2, w[3], 12);
    R11(a1, b1, c1, d1, e1, w[15], 8);
    R12(a2, b2, c2, d2, e2, w[12], 6);
    R21(e1, a1, b1, c1, d1, w[7], 7);
    R22(e2, a2, b2, c2, d2, w[6], 9);
    R21(d1, e1, a1, b1, c1, w[4], 6);
    R22(d2, e2, a2, b2, c2, w[11], 13);
    R21(c1, d1, e1, a1, b1, w[13], 8);
    R22(c2, d2, e2, a2, b2, w[3], 15);
    R21(b1, c1, d1, e1, a1, w[1], 13);
    R22(b2, c2, d2, e2, a2, w[7], 7);
    R21(a1, b1, c1, d1, e1, w[10], 11);
    R22(a2, b2, c2, d2, e2, w[0], 12);
    R21(e1, a1, b1, c1, d1, w[6], 9);
    R22(e2, a2, b2, c2, d2, w[13], 8);
    R21(d1, e1, a1, b1, c1, w[15], 7);
    R22(d2, e2, a2, b2, c2, w[5], 9);
    R21(c1, d1, e1, a1, b1, w[3], 15);
    R22(c2, d2, e2, a2, b2, w[10], 11);
    R21(b1, c1, d1, e1, a1, w[12], 7);
    R22(b2, c2, d2, e2, a2, w[14], 7);
    R21(a1, b1, c1, d1, e1, w[0], 12);
    R22(a2, b2, c2, d2, e2, w[15], 7);
    R21(e1, a1, b1, c1, d1, w[9], 15);
    R22(e2, a2, b2, c2, d2, w[8], 12);
    R21(d1, e1, a1, b1, c1, w[5], 9);
    R22(d2, e2, a2, b2, c2, w[12], 7);
    R21(c1, d1, e1, a1, b1, w[2], 11);
    R22(c2, d2, e2, a2, b2, w[4], 6);
    R21(b1, c1, d1, e1, a1, w[14], 7);
    R22(b2, c2, d2, e2, a2, w[9], 15);
    R21(a1, b1, c1, d1, e1, w[11], 13);
    R22(a2, b2, c2, d2, e2, w[1], 13);
    R21(e1, a1, b1, c1, d1, w[8], 12);
    R22(e2, a2, b2, c2, d2, w[2], 11);
    R31(d1, e1, a1, b1, c1, w[3], 11);
    R32(d2, e2, a2, b2, c2, w[15], 9);
    R31(c1, d1, e1, a1, b1, w[10], 13);
    R32(c2, d2, e2, a2, b2, w[5], 7);
    R31(b1, c1, d1, e1, a1, w[14], 6);
    R32(b2, c2, d2, e2, a2, w[1], 15);
    R31(a1, b1, c1, d1, e1, w[4], 7);
    R32(a2, b2, c2, d2, e2, w[3], 11);
    R31(e1, a1, b1, c1, d1, w[9], 14);
    R32(e2, a2, b2, c2, d2, w[7], 8);
    R31(d1, e1, a1, b1, c1, w[15], 9);
    R32(d2, e2, a2, b2, c2, w[14], 6);
    R31(c1, d1, e1, a1, b1, w[8], 13);
    R32(c2, d2, e2, a2, b2, w[6], 6);
    R31(b1, c1, d1, e1, a1, w[1], 15);
    R32(b2, c2, d2, e2, a2, w[9], 14);
    R31(a1, b1, c1, d1, e1, w[2], 14);
    R32(a2, b2, c2, d2, e2, w[11], 12);
    R31(e1, a1, b1, c1, d1, w[7], 8);
    R32(e2, a2, b2, c2, d2, w[8], 13);
    R31(d1, e1, a1, b1, c1, w[0], 13);
    R32(d2, e2, a2, b2, c2, w[12], 5);
    R31(c1, d1, e1, a1, b1, w[6], 6);
    R32(c2, d2, e2, a2, b2, w[2], 14);
    R31(b1, c1, d1, e1, a1, w[13], 5);
    R32(b2, c2, d2, e2, a2, w[10], 13);
    R31(a1, b1, c1, d1, e1, w[11], 12);
    R32(a2, b2, c2, d2, e2, w[0], 13);
    R31(e1, a1, b1, c1, d1, w[5], 7);
    R32(e2, a2, b2, c2, d2, w[4], 7);
    R31(d1, e1, a1, b1, c1, w[12], 5);
    R32(d2, e2, a2, b2, c2, w[13], 5);
    R41(c1, d1, e1, a1, b1, w[1], 11);
    R42(c2, d2, e2, a2, b2, w[8], 15);
    R41(b1, c1, d1, e1, a1, w[9], 12);
    R42(b2, c2, d2, e2, a2, w[6], 5);
    R41(a1, b1, c1, d1, e1, w[11], 14);
    R42(a2, b2, c2, d2, e2, w[4], 8);
    R41(e1, a1, b1, c1, d1, w[10], 15);
    R42(e2, a2, b2, c2, d2, w[1], 11);
    R41(d1, e1, a1, b1, c1, w[0], 14);
    R42(d2, e2, a2, b2, c2, w[3], 14);
    R41(c1, d1, e1, a1, b1, w[8], 15);
    R42(c2, d2, e2, a2, b2, w[11], 14);
    R41(b1, c1, d1, e1, a1, w[12], 9);
    R42(b2, c2, d2, e2, a2, w[15], 6);
    R41(a1, b1, c1, d1, e1, w[4], 8);
    R42(a2, b2, c2, d2, e2, w[0], 14);
    R41(e1, a1, b1, c1, d1, w[13], 9);
    R42(e2, a2, b2, c2, d2, w[5], 6);
    R41(d1, e1, a1, b1, c1, w[3], 14);
    R42(d2, e2, a2, b2, c2, w[12], 9);
    R41(c1, d1, e1, a1, b1, w[7], 5);
    R42(c2, d2, e2, a2, b2, w[2], 12);
    R41(b1, c1, d1, e1, a1, w[15], 6);
    R42(b2, c2, d2, e2, a2, w[13], 9);
    R41(a1, b1, c1, d1, e1, w[14], 8);
    R42(a2, b2, c2, d2, e2, w[9], 12);
    R41(e1, a1, b1, c1, d1, w[5], 6);
    R42(e2, a2, b2, c2, d2, w[7], 5);
    R41(d1, e1, a1, b1, c1, w[6], 5);
    R42(d2, e2, a2, b2, c2, w[10], 15);
    R41(c1, d1, e1, a1, b1, w[2], 12);
    R42(c2, d2, e2, a2, b2, w[14], 8);
    R51(b1, c1, d1, e1, a1, w[4], 9);
    R52(b2, c2, d2, e2, a2, w[12], 8);
    R51(a1, b1, c1, d1, e1, w[0], 15);
    R52(a2, b2, c2, d2, e2, w[15], 5);
    R51(e1, a1, b1, c1, d1, w[5], 5);
    R52(e2, a2, b2, c2, d2, w[10], 12);
    R51(d1, e1, a1, b1, c1, w[9], 11);
    R52(d2, e2, a2, b2, c2, w[4], 9);
    R51(c1, d1, e1, a1, b1, w[7], 6);
    R52(c2, d2, e2, a2, b2, w[1], 12);
    R51(b1, c1, d1, e1, a1, w[12], 8);
    R52(b2, c2, d2, e2, a2, w[5], 5);
    R51(a1, b1, c1, d1, e1, w[2], 13);
    R52(a2, b2, c2, d2, e2, w[8], 14);
    R51(e1, a1, b1, c1, d1, w[10], 12);
    R52(e2, a2, b2, c2, d2, w[7], 6);
    R51(d1, e1, a1, b1, c1, w[14], 5);
    R52(d2, e2, a2, b2, c2, w[6], 8);
    R51(c1, d1, e1, a1, b1, w[1], 12);
    R52(c2, d2, e2, a2, b2, w[2], 13);
    R51(b1, c1, d1, e1, a1, w[3], 13);
    R52(b2, c2, d2, e2, a2, w[13], 6);
    R51(a1, b1, c1, d1, e1, w[8], 14);
    R52(a2, b2, c2, d2, e2, w[14], 5);
    R51(e1, a1, b1, c1, d1, w[11], 11);
    R52(e2, a2, b2, c2, d2, w[0], 15);
    R51(d1, e1, a1, b1, c1, w[6], 8);
    R52(d2, e2, a2, b2, c2, w[3], 13);
    R51(c1, d1, e1, a1, b1, w[15], 5);
    R52(c2, d2, e2, a2, b2, w[9], 11);
    R51(b1, c1, d1, e1, a1, w[13], 6);
    R52(b2, c2, d2, e2, a2, w[11], 11);

  // Standard RIPEMD160 cross-line finalization (five 32-bit words).
  V out0=vaddq_u32(vaddq_u32(h1,c1),d2);
  V out1=vaddq_u32(vaddq_u32(h2,d1),e2);
  V out2=vaddq_u32(vaddq_u32(h3,e1),a2);
  V out3=vaddq_u32(vaddq_u32(h4,a1),b2);
  V out4=vaddq_u32(vaddq_u32(h0,b1),c2);

  uint32_t results[5][4];
  vst1q_u32(results[0],out0);
  vst1q_u32(results[1],out1);
  vst1q_u32(results[2],out2);
  vst1q_u32(results[3],out3);
  vst1q_u32(results[4],out4);
  uint8_t *dst[4]={dst0,dst1,dst2,dst3};
  for (int lane=0;lane<4;lane++) {
    const uint32_t words[5]={
      results[0][lane],results[1][lane],results[2][lane],
      results[3][lane],results[4][lane]
    };
    std::memcpy(dst[lane],words,20);
  }
}
#undef ROL
#undef f1
#undef f2
#undef f3
#undef f4
#undef f5
#undef ROUND
#undef R11
#undef R21
#undef R31
#undef R41
#undef R51
#undef R12
#undef R22
#undef R32
#undef R42
#undef R52
} // namespace

void ripemd160sse_32(uint8_t *i0,uint8_t *i1,uint8_t *i2,uint8_t *i3,
                      uint8_t *d0,uint8_t *d1,uint8_t *d2,uint8_t *d3) {
  transform4(i0,i1,i2,i3,d0,d1,d2,d3);
}
