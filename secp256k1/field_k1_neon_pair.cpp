// Experimental secp256k1 subtraction across two independent points using
// two NEON 64-bit lanes. A, B must be canonical residues 0 <= x < p.
// p = 2^256 - (2^32 + 977), so a negative wrapped 256-bit difference
// is canonicalized by subtracting C = 2^32 + 977 from the wrapped value.
// Distinct output locations required; inputs may overlap each other.
#include "field_k1_neon_pair.h"
#include <arm_neon.h>
#include <cstdint>

#if !defined(__aarch64__)
#error "NEON paired ECC field subtraction requires AArch64"
#endif

void ecc_modsub_2_neon(Int *out0, Int *out1,
                      const Int *a0, const Int *a1, const Int *b) {
  constexpr uint64_t C = 0x1000003d1ULL;
  uint64x2_t diff[4];
  uint64x2_t borrow_mask = vdupq_n_u64(0);
  for (unsigned k = 0; k < 4; ++k) {
    const uint64x2_t a = {a0->bits64[k], a1->bits64[k]};
    const uint64x2_t bb = vdupq_n_u64(b->bits64[k]);
    const uint64x2_t prev_borrow = vshrq_n_u64(borrow_mask, 63);
    diff[k] = vsubq_u64(vsubq_u64(a, bb), prev_borrow);
    // unsigned a - b - carry borrows if a<b, or if a==b and carry==1
    borrow_mask = vorrq_u64(vcgtq_u64(bb,a),
                            vandq_u64(vceqq_u64(a,bb), borrow_mask));
  }
  const uint64x2_t correction = vandq_u64(vshrq_n_u64(borrow_mask,63),
                                          vdupq_n_u64(C));
  // Applying +p to the signed 256-bit difference is subtracting C
  // from the wrapped low 256-bit result for the lanes with borrow.
  uint64x2_t carry_mask = vcgtq_u64(correction,diff[0]);
  diff[0] = vsubq_u64(diff[0],correction);
  for (unsigned k = 1; k < 4; ++k) {
    const uint64x2_t carry = vshrq_n_u64(carry_mask,63);
    carry_mask = vcgtq_u64(carry,diff[k]);
    diff[k] = vsubq_u64(diff[k],carry);
  }

  for (unsigned k = 0; k < 4; ++k) {
    out0->bits64[k] = vgetq_lane_u64(diff[k],0);
    out1->bits64[k] = vgetq_lane_u64(diff[k],1);
  }
  out0->bits64[4] = 0;
  out1->bits64[4] = 0;
}
