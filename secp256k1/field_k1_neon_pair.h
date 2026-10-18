// Experimental two-lane secp256k1 field subtraction.
// AArch64 NEON parallelizes two *independent* residues (P+G, P-G).
// This is NOT a SIMD 64x64->128 multiplication implementation.
#pragma once
#include "Int.h"

void ecc_modsub_2_neon(Int *out0, Int *out1,
                      const Int *a0, const Int *a1, const Int *b);
