// Experiment-only two-independent-4x64 secp256k1 field products.
// Shares one operand (already inverted affine x delta). No default linkage.
// Distinct output buffers; input/output aliasing intentionally not supported.
#pragma once
#include <cstdint>
void field_k1_arm64_mul2(uint64_t out_plus[5], uint64_t out_minus[5],
                         const uint64_t plus[5], const uint64_t minus[5],
                         const uint64_t denominator_inverse[5]);
void field_k1_arm64_mul2_fold(uint64_t out_plus[5], uint64_t out_minus[5],
                              const uint64_t plus[5], const uint64_t minus[5],
                              const uint64_t denominator_inverse[5]);

/* Full point-pair pipeline: arbitrary independent products a0*b0 and a1*b1.
   Not alias-safe. Used for BOTH Y-coordinate field products in R7. */
void field_k1_arm64_mul2_independent(uint64_t out0[5],uint64_t out1[5],
                                    const uint64_t a0[5],const uint64_t b0[5],
                                    const uint64_t a1[5],const uint64_t b1[5]);
void field_k1_arm64_mul2_independent_fold(uint64_t out0[5],uint64_t out1[5],
                                         const uint64_t a0[5],const uint64_t b0[5],
                                         const uint64_t a1[5],const uint64_t b1[5]);
