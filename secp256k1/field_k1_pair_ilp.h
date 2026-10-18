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
