/*
 * Experimental OpenSSL-backed four-way hash adapter for ARM64.
 *
 * Unlike the scalar adapter this delegates SHA256 to OpenSSL, which may
 * select the CPU's SHA2 instructions at runtime. RIPEMD160 remains software.
 * This is a comparison backend, not a change to the default ARM64 build.
 */
#include <cstddef>
#include <cstdint>

#include <openssl/sha.h>
#include <openssl/ripemd.h>

#include "sha256.h"
#include "ripemd160.h"

namespace {

void sha_words(const uint32_t *words, size_t message_length, uint8_t *digest) {
  uint8_t message[65];
  // KEYBUFF* creates big-endian message words for the compressed/uncompressed
  // public-key path; unpack only meaningful bytes (33 or 65).
  for (size_t i = 0; i < message_length; ++i) {
    message[i] = static_cast<uint8_t>(words[i / 4] >>
                                      (24 - 8 * (i % 4)));
  }
  SHA256(message, message_length, digest);
}

} // namespace

void sha256sse_1B(uint32_t *i0, uint32_t *i1, uint32_t *i2, uint32_t *i3,
                  uint8_t *d0, uint8_t *d1, uint8_t *d2, uint8_t *d3) {
  sha_words(i0, 33, d0);
  sha_words(i1, 33, d1);
  sha_words(i2, 33, d2);
  sha_words(i3, 33, d3);
}

void sha256sse_2B(uint32_t *i0, uint32_t *i1, uint32_t *i2, uint32_t *i3,
                  uint8_t *d0, uint8_t *d1, uint8_t *d2, uint8_t *d3) {
  sha_words(i0, 65, d0);
  sha_words(i1, 65, d1);
  sha_words(i2, 65, d2);
  sha_words(i3, 65, d3);
}

void ripemd160sse_32(uint8_t *i0, uint8_t *i1, uint8_t *i2, uint8_t *i3,
                      uint8_t *d0, uint8_t *d1, uint8_t *d2, uint8_t *d3) {
  RIPEMD160(i0, 32, d0);
  RIPEMD160(i1, 32, d1);
  RIPEMD160(i2, 32, d2);
  RIPEMD160(i3, 32, d3);
}
