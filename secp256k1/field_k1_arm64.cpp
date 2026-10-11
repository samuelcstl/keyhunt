/*
 * AArch64-oriented secp256k1 prime-field arithmetic experiment.
 * p = 2^256 - C, C = 2^32 + 977.
 * Four 64-bit LE limbs in, five-limb Int representation out (out[4] = 0).
 * Inputs must be canonical residues (<p), as in upstream ModMulK1.
 * The output may alias either input.
 *
 * Deliberately isolated behind a build target: the baseline IntMod remains
 * unchanged. GCC on Cortex-A76 lowers 64x64->128 to MUL/UMULH.
 */
#include <cstdint>
#include <climits>

#if !defined(__aarch64__)
#error "This field experiment is only intended for AArch64"
#endif

namespace {
using U128 = unsigned __int128;
constexpr uint64_t C = 0x1000003d1ULL;
constexpr uint64_t P0 = 0xfffffffefffffc2fULL;

static inline void reduce_k1(uint64_t out[5], const uint64_t t[8]) {
    uint64_t z[4];
    U128 carry = 0;
    // 2^256 == C modulo p. Fold upper product half into lower.
    for (unsigned k = 0; k != 4; ++k) {
        const U128 v = U128(t[4 + k]) * C + t[k] + carry;
        z[k] = static_cast<uint64_t>(v);
        carry = v >> 64;
    }
    // The first fold leaves an approximately 33-bit fifth limb. Folding it
    // again leaves at most a one-bit carry, which must still be handled.
    while (carry) {
        U128 v = U128(static_cast<uint64_t>(carry)) * C + z[0];
        z[0] = static_cast<uint64_t>(v);
        carry = v >> 64;
        for (unsigned k = 1; k < 4; ++k) {
            v = U128(z[k]) + carry;
            z[k] = static_cast<uint64_t>(v);
            carry = v >> 64;
        }
    }
    // Canonical output is in [0,p), subtract p at most once.
    if (z[3] == UINT64_MAX && z[2] == UINT64_MAX &&
        z[1] == UINT64_MAX && z[0] >= P0) {
        z[0] -= P0;
        z[1] = z[2] = z[3] = 0;
    }
    out[0] = z[0]; out[1] = z[1];
    out[2] = z[2]; out[3] = z[3]; out[4] = 0;
}

static inline void product_4x4(uint64_t t[8], const uint64_t a[5],
                               const uint64_t b[5]) {
    for (unsigned k = 0; k != 8; ++k) t[k] = 0;
    // 16 64-bit products, with exactly one carried accumulator per row.
    // Each sum <= (2^64-1)^2 + 2*(2^64-1) = 2^128-1.
    for (unsigned i = 0; i != 4; ++i) {
        U128 carry = 0;
        for (unsigned j = 0; j != 4; ++j) {
            const U128 v = U128(a[j]) * b[i] + t[i + j] + carry;
            t[i + j] = static_cast<uint64_t>(v);
            carry = v >> 64;
        }
        t[i + 4] = static_cast<uint64_t>(carry);
    }
}

static inline void product_square(uint64_t t[8], const uint64_t a[5]) {
    // Symmetric Comba columns: only 10 distinct 64x64 products.
    // Cross-products contribute twice; any 128-bit overflow is explicitly
    // retained above the low accumulator and carried into the next column.
    U128 carry = 0;
    for (unsigned k = 0; k != 7; ++k) {
        U128 accum = carry;
        uint64_t upper = 0;
        for (unsigned i = 0; i != 4; ++i) {
            const int j = int(k) - int(i);
            if (j < int(i) || j > 3) continue;
            const U128 product = U128(a[i]) * a[j];
            const U128 next = accum + product;
            upper += next < accum;
            accum = next;
            if (i != unsigned(j)) {
                const U128 twice = accum + product;
                upper += twice < accum;
                accum = twice;
            }
        }
        t[k] = static_cast<uint64_t>(accum);
        carry = (accum >> 64) + (U128(upper) << 64);
    }
    t[7] = static_cast<uint64_t>(carry);
}
// Column-ordered Comba experiment: each 64-bit product is used once,
// with no repeated writes of partially accumulated 512-bit limbs.
// Track carries beyond 128 bits explicitly for middle columns.
static inline void product_4x4_comba(uint64_t t[8],
                                      const uint64_t a[5],
                                      const uint64_t b[5]) {
    const uint64_t a0 = a[0], b0 = b[0];
    const uint64_t a1 = a[1], b1 = b[1];
    const uint64_t a2 = a[2], b2 = b[2];
    const uint64_t a3 = a[3], b3 = b[3];
    U128 carry = 0;
    {
        U128 sum = carry;
        uint64_t overflow = 0;
        {
            const U128 product = U128(a0) * b0;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        t[0] = static_cast<uint64_t>(sum);
        carry = (sum >> 64) + (U128(overflow) << 64);
    }
    {
        U128 sum = carry;
        uint64_t overflow = 0;
        {
            const U128 product = U128(a0) * b1;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        {
            const U128 product = U128(a1) * b0;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        t[1] = static_cast<uint64_t>(sum);
        carry = (sum >> 64) + (U128(overflow) << 64);
    }
    {
        U128 sum = carry;
        uint64_t overflow = 0;
        {
            const U128 product = U128(a0) * b2;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        {
            const U128 product = U128(a1) * b1;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        {
            const U128 product = U128(a2) * b0;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        t[2] = static_cast<uint64_t>(sum);
        carry = (sum >> 64) + (U128(overflow) << 64);
    }
    {
        U128 sum = carry;
        uint64_t overflow = 0;
        {
            const U128 product = U128(a0) * b3;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        {
            const U128 product = U128(a1) * b2;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        {
            const U128 product = U128(a2) * b1;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        {
            const U128 product = U128(a3) * b0;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        t[3] = static_cast<uint64_t>(sum);
        carry = (sum >> 64) + (U128(overflow) << 64);
    }
    {
        U128 sum = carry;
        uint64_t overflow = 0;
        {
            const U128 product = U128(a1) * b3;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        {
            const U128 product = U128(a2) * b2;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        {
            const U128 product = U128(a3) * b1;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        t[4] = static_cast<uint64_t>(sum);
        carry = (sum >> 64) + (U128(overflow) << 64);
    }
    {
        U128 sum = carry;
        uint64_t overflow = 0;
        {
            const U128 product = U128(a2) * b3;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        {
            const U128 product = U128(a3) * b2;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        t[5] = static_cast<uint64_t>(sum);
        carry = (sum >> 64) + (U128(overflow) << 64);
    }
    {
        U128 sum = carry;
        uint64_t overflow = 0;
        {
            const U128 product = U128(a3) * b3;
            const U128 previous = sum;
            sum += product;
            overflow += sum < previous;
        }
        t[6] = static_cast<uint64_t>(sum);
        carry = (sum >> 64) + (U128(overflow) << 64);
    }
    t[7] = static_cast<uint64_t>(carry);
}

} // namespace

void field_k1_arm64_mul(uint64_t out[5], const uint64_t a[5],
                         const uint64_t b[5]) {
    uint64_t t[8];
    product_4x4(t, a, b);
    reduce_k1(out, t);
}

void field_k1_arm64_square(uint64_t out[5], const uint64_t a[5]) {
    uint64_t t[8];
    product_square(t, a);
    reduce_k1(out, t);
}

// Same canonical reduction and alias semantics as the row-product kernel.
void field_k1_arm64_mul_comba(uint64_t out[5], const uint64_t a[5],
                               const uint64_t b[5]) {
    uint64_t t[8];
    product_4x4_comba(t, a, b);
    reduce_k1(out, t);
}
