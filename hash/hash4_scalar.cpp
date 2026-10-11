/*
 * Scalar implementation of Keyhunt's four-way SHA256/RIPEMD160 interfaces
 * for ARM64. The inputs for sha256sse_* are already-padded, big-endian
 * message words as produced by KEYBUFFCOMP / KEYBUFFUNCOMP / KEYBUFFPREFIX.
 *
 * Start with a correctness baseline, not an unverified SIMD port. Once the
 * ARM64 fixed-width ECC backend is validated, these functions are candidates
 * for replacement with NEON implementations.
 */
#include <cstddef>
#include <cstdint>

#include "sha256.h"
#include "ripemd160.h"

namespace {

void hash_words(const uint32_t *words, size_t message_length, uint8_t *digest) {
  // Compressed public key: 33 bytes; uncompressed: 65 bytes.
  alignas(16) uint8_t message[65];
  for (size_t i = 0; i < message_length; ++i) {
    message[i] = static_cast<uint8_t>(words[i / 4] >>
                                       (24 - 8 * (i % 4)));
  }
  sha256(message, message_length, digest);
}

} // namespace

void sha256sse_1B(uint32_t *i0, uint32_t *i1, uint32_t *i2, uint32_t *i3,
                  uint8_t *d0, uint8_t *d1, uint8_t *d2, uint8_t *d3) {
  hash_words(i0, 33, d0);
  hash_words(i1, 33, d1);
  hash_words(i2, 33, d2);
  hash_words(i3, 33, d3);
}

void sha256sse_2B(uint32_t *i0, uint32_t *i1, uint32_t *i2, uint32_t *i3,
                  uint8_t *d0, uint8_t *d1, uint8_t *d2, uint8_t *d3) {
  hash_words(i0, 65, d0);
  hash_words(i1, 65, d1);
  hash_words(i2, 65, d2);
  hash_words(i3, 65, d3);
}

void ripemd160sse_32(uint8_t *i0, uint8_t *i1, uint8_t *i2, uint8_t *i3,
                      uint8_t *d0, uint8_t *d1, uint8_t *d2, uint8_t *d3) {
  ripemd160(i0, 32, d0);
  ripemd160(i1, 32, d1);
  ripemd160(i2, 32, d2);
  ripemd160(i3, 32, d3);
}
