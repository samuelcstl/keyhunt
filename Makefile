default:
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -flto -c oldbloom/bloom.cpp -o oldbloom.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -flto -c bloom/bloom.cpp -o bloom.o
	gcc -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-unused-parameter -Ofast -ftree-vectorize -c base58/base58.c -o base58.o
	gcc -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Ofast -ftree-vectorize -c rmd160/rmd160.c -o rmd160.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c sha3/sha3.c -o sha3.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c sha3/keccak.c -o keccak.o
	gcc -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Ofast -ftree-vectorize -c xxhash/xxhash.c -o xxhash.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c util.c -o util.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c secp256k1/Int.cpp -o Int.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c secp256k1/Point.cpp -o Point.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c secp256k1/SECP256K1.cpp -o SECP256K1.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c secp256k1/IntMod.cpp -o IntMod.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -flto -c secp256k1/Random.cpp -o Random.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -flto -c secp256k1/IntGroup.cpp -o IntGroup.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -o hash/ripemd160.o -ftree-vectorize -flto -c hash/ripemd160.cpp
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -o hash/sha256.o -ftree-vectorize -flto -c hash/sha256.cpp
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -o hash/ripemd160_sse.o -ftree-vectorize -flto -c hash/ripemd160_sse.cpp
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -o hash/sha256_sse.o -ftree-vectorize -flto -c hash/sha256_sse.cpp
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -o keyhunt keyhunt.cpp base58.o rmd160.o hash/ripemd160.o hash/ripemd160_sse.o hash/sha256.o hash/sha256_sse.o bloom.o oldbloom.o xxhash.o util.o Int.o  Point.o SECP256K1.o  IntMod.o  Random.o IntGroup.o sha3.o keccak.o  -lm -lpthread
	rm -r *.o
clean:
	rm keyhunt
legacy:
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -flto -c oldbloom/bloom.cpp -o oldbloom.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -flto -c bloom/bloom.cpp -o bloom.o
	gcc -march=native -mtune=native -Wno-unused-result -Ofast -ftree-vectorize -c base58/base58.c -o base58.o
	gcc -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -c xxhash/xxhash.c -o xxhash.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -c util.c -o util.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -c sha3/sha3.c -o sha3.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -c sha3/keccak.c -o keccak.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -c hashing.c -o hashing.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -c gmp256k1/Int.cpp -o Int.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -c gmp256k1/Point.cpp -o Point.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -c gmp256k1/GMP256K1.cpp -o GMP256K1.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -c gmp256k1/IntMod.cpp -o IntMod.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -flto -c gmp256k1/Random.cpp -o Random.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -flto -c gmp256k1/IntGroup.cpp -o IntGroup.o
	g++ -march=native -mtune=native -Wall -Wextra -Ofast -ftree-vectorize -o keyhunt keyhunt_legacy.cpp base58.o bloom.o oldbloom.o xxhash.o util.o Int.o  Point.o GMP256K1.o  IntMod.o  IntGroup.o Random.o hashing.o sha3.o keccak.o -lm -lpthread -lcrypto -lgmp	
	rm -r *.o
bsgsd:
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -flto -c oldbloom/bloom.cpp -o oldbloom.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -flto -c bloom/bloom.cpp -o bloom.o
	gcc -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-unused-parameter -Ofast -ftree-vectorize -c base58/base58.c -o base58.o
	gcc -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Ofast -ftree-vectorize -c rmd160/rmd160.c -o rmd160.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c sha3/sha3.c -o sha3.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c sha3/keccak.c -o keccak.o
	gcc -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Ofast -ftree-vectorize -c xxhash/xxhash.c -o xxhash.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c util.c -o util.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c secp256k1/Int.cpp -o Int.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c secp256k1/Point.cpp -o Point.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c secp256k1/SECP256K1.cpp -o SECP256K1.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -c secp256k1/IntMod.cpp -o IntMod.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -flto -c secp256k1/Random.cpp -o Random.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -flto -c secp256k1/IntGroup.cpp -o IntGroup.o
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -o hash/ripemd160.o -ftree-vectorize -flto -c hash/ripemd160.cpp
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -o hash/sha256.o -ftree-vectorize -flto -c hash/sha256.cpp
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -o hash/ripemd160_sse.o -ftree-vectorize -flto -c hash/ripemd160_sse.cpp
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -o hash/sha256_sse.o -ftree-vectorize -flto -c hash/sha256_sse.cpp
	g++ -m64 -march=native -mtune=native -mssse3 -Wall -Wextra -Wno-deprecated-copy -Ofast -ftree-vectorize -o bsgsd bsgsd.cpp base58.o rmd160.o hash/ripemd160.o hash/ripemd160_sse.o hash/sha256.o hash/sha256_sse.o bloom.o oldbloom.o xxhash.o util.o Int.o  Point.o SECP256K1.o  IntMod.o  Random.o IntGroup.o sha3.o keccak.o  -lm -lpthread
	rm -r *.o

# Native Cortex-A76 experiment. Keep the standard x86 build and GMP legacy
# targets unchanged. Objects live in build/arm64 so builds cannot mix backends.
ARM64_CXX ?= g++
ARM64_CC ?= gcc
ARM64_CXXFLAGS ?= -O3 -mcpu=cortex-a76 -std=gnu++17 -Wall -Wextra -Wno-deprecated-copy -fno-strict-aliasing -flto
ARM64_CFLAGS ?= -O3 -mcpu=cortex-a76 -Wall -Wextra -fno-strict-aliasing -flto

ARM64_CPP_SRCS := keyhunt.cpp oldbloom/bloom.cpp bloom/bloom.cpp \
  sha3/sha3.c sha3/keccak.c util.c \
  secp256k1/Int.cpp secp256k1/Point.cpp secp256k1/SECP256K1.cpp \
  secp256k1/IntMod.cpp secp256k1/Random.cpp secp256k1/IntGroup.cpp \
  hash/sha256.cpp hash/ripemd160.cpp hash/hash4_scalar.cpp
ARM64_C_SRCS := base58/base58.c rmd160/rmd160.c xxhash/xxhash.c
ARM64_CPP_OBJS := $(patsubst %.cpp,build/arm64/%.o,$(filter %.cpp,$(ARM64_CPP_SRCS))) \
  $(patsubst %.c,build/arm64/%.o,$(filter %.c,$(ARM64_CPP_SRCS)))
ARM64_C_OBJS := $(patsubst %.c,build/arm64/%.o,$(ARM64_C_SRCS))

.PHONY: arm64 arm64-clean arm64-test
arm64: keyhunt-arm64

keyhunt-arm64: $(ARM64_CPP_OBJS) $(ARM64_C_OBJS)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -o $@ $^ -lm -lpthread

build/arm64/%.o: %.cpp
	@mkdir -p $(dir $@)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -c $< -o $@

# These upstream .c sources were compiled as C++ by the main Makefile.
build/arm64/sha3/%.o: sha3/%.c
	@mkdir -p $(dir $@)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -x c++ -c $< -o $@

build/arm64/util.o: util.c
	@mkdir -p $(dir $@)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -x c++ -c $< -o $@

build/arm64/base58/%.o: base58/%.c
	@mkdir -p $(dir $@)
	$(ARM64_CC) $(ARM64_CFLAGS) -c $< -o $@

build/arm64/rmd160/%.o: rmd160/%.c
	@mkdir -p $(dir $@)
	$(ARM64_CC) $(ARM64_CFLAGS) -c $< -o $@

build/arm64/xxhash/%.o: xxhash/%.c
	@mkdir -p $(dir $@)
	$(ARM64_CC) $(ARM64_CFLAGS) -c $< -o $@

arm64-test: arm64
	bash tests/arm64-smoke.sh
	python3 tests/arm64-vectors.py
	bash tests/arm64-solved-fixtures.sh

arm64-clean:
	rm -rf build/arm64 keyhunt-arm64

# OpenSSL-backed four-way hash experiment. Shares fixed-width ECC objects
# with arm64; changing only the four-lane hash implementation.
ARM64_OPENSSL_OBJS := $(filter-out build/arm64/hash/hash4_scalar.o,$(ARM64_CPP_OBJS)) \
  $(ARM64_C_OBJS) build/arm64/hash/hash4_openssl.o

.PHONY: arm64-openssl arm64-openssl-test
arm64-openssl: keyhunt-arm64-openssl

keyhunt-arm64-openssl: $(ARM64_OPENSSL_OBJS)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -o $@ $^ -lm -lpthread -lcrypto

arm64-openssl-test: arm64-openssl
	KEYHUNT_BIN=keyhunt-arm64-openssl bash tests/arm64-smoke.sh
	KEYHUNT_BIN=keyhunt-arm64-openssl python3 tests/arm64-vectors.py
	KEYHUNT_BIN=keyhunt-arm64-openssl bash tests/arm64-solved-fixtures.sh

# Explicit ARMv8 SHA2 instructions, without libcrypto or SSE.
# Only the SHA2 adapter is compiled with the SHA2 feature requirement.
ARM64_SHA2_CXXFLAGS := $(ARM64_CXXFLAGS) -march=armv8.2-a+sha2
ARM64_SHA2_OBJS := $(filter-out build/arm64/hash/hash4_scalar.o,$(ARM64_CPP_OBJS)) \
  $(ARM64_C_OBJS) build/arm64/hash/hash4_arm_sha2.o

.PHONY: arm64-sha2 arm64-sha2-test
arm64-sha2: keyhunt-arm64-sha2

keyhunt-arm64-sha2: $(ARM64_SHA2_OBJS)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -o $@ $^ -lm -lpthread

build/arm64/hash/hash4_arm_sha2.o: hash/hash4_arm_sha2.cpp
	@mkdir -p $(dir $@)
	$(ARM64_CXX) $(ARM64_SHA2_CXXFLAGS) -c $< -o $@

arm64-sha2-test: arm64-sha2
	KEYHUNT_BIN=keyhunt-arm64-sha2 bash tests/arm64-smoke.sh
	KEYHUNT_BIN=keyhunt-arm64-sha2 python3 tests/arm64-vectors.py
	KEYHUNT_BIN=keyhunt-arm64-sha2 bash tests/arm64-solved-fixtures.sh

# SHA256H/H2 stays identical to make arm64-sha2; only RIPEMD160 changes.
# Compile a variant of the SHA2 adapter without its scalar RIPEMD160 symbol
# and link the four-way NEON implementation instead.
ARM64_SHA2_NEON_OBJS := $(filter-out build/arm64/hash/hash4_scalar.o,$(ARM64_CPP_OBJS)) \
  $(ARM64_C_OBJS) build/arm64/hash/hash4_arm_sha2_neon.o \
  build/arm64/hash/ripemd160_neon4.o

.PHONY: arm64-sha2-neon arm64-sha2-neon-test
arm64-sha2-neon: keyhunt-arm64-sha2-neon

keyhunt-arm64-sha2-neon: $(ARM64_SHA2_NEON_OBJS)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -o $@ $^ -lm -lpthread

build/arm64/hash/hash4_arm_sha2_neon.o: hash/hash4_arm_sha2.cpp
	@mkdir -p $(dir $@)
	$(ARM64_CXX) $(ARM64_SHA2_CXXFLAGS) -DKEYHUNT_NEON_RIPEMD160 -c $< -o $@

build/arm64/hash/ripemd160_neon4.o: hash/ripemd160_neon4.cpp
	@mkdir -p $(dir $@)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -c $< -o $@

build/arm64/ripemd160-neon-selftest: tests/arm64-ripemd160-neon.cpp build/arm64/hash/ripemd160_neon4.o
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -o $@ $^ -lcrypto

arm64-sha2-neon-test: arm64-sha2-neon build/arm64/ripemd160-neon-selftest
	./build/arm64/ripemd160-neon-selftest
	KEYHUNT_BIN=keyhunt-arm64-sha2-neon bash tests/arm64-smoke.sh
	KEYHUNT_BIN=keyhunt-arm64-sha2-neon python3 tests/arm64-vectors.py
	KEYHUNT_BIN=keyhunt-arm64-sha2-neon bash tests/arm64-solved-fixtures.sh

# SHA2 schedule/round fusion adopted from btc-sha256d-engine.
# Distinct binary from the hardware-SHA2 + NEON baseline for exact A/B tests.
ARM64_SU2_CORE_OBJS := $(filter-out build/arm64/hash/hash4_scalar.o,$(ARM64_CPP_OBJS)) \
  $(ARM64_C_OBJS) build/arm64/hash/hash4_arm_sha2_su2.o \
  build/arm64/hash/ripemd160_neon4.o
ARM64_SU2_CENTER_OBJS := $(filter-out build/arm64/keyhunt.o,$(ARM64_SU2_CORE_OBJS)) \
  build/arm64/keyhunt-center.o

.PHONY: arm64-sha2-neon-su2 arm64-sha2-neon-su2-test
.PHONY: arm64-sha2-neon-su2-center arm64-sha2-neon-su2-center-test

arm64-sha2-neon-su2: keyhunt-arm64-sha2-neon-su2

keyhunt-arm64-sha2-neon-su2: $(ARM64_SU2_CORE_OBJS)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -o $@ $^ -lm -lpthread

build/arm64/hash/hash4_arm_sha2_su2.o: hash/hash4_arm_sha2_su2.cpp
	@mkdir -p $(dir $@)
	$(ARM64_CXX) $(ARM64_SHA2_CXXFLAGS) -c $< -o $@

build/arm64/keyhunt-center.o: keyhunt.cpp
	@mkdir -p $(dir $@)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -DKEYHUNT_INCREMENTAL_CENTER -c $< -o $@

arm64-sha2-neon-su2-center: keyhunt-arm64-sha2-neon-su2-center

keyhunt-arm64-sha2-neon-su2-center: $(ARM64_SU2_CENTER_OBJS)
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -o $@ $^ -lm -lpthread

build/arm64/sha256-su2-selftest: tests/arm64-sha256-su2.cpp build/arm64/hash/hash4_arm_sha2_su2.o
	$(ARM64_CXX) $(ARM64_CXXFLAGS) -o $@ $^ -lcrypto

arm64-sha2-neon-su2-test: arm64-sha2-neon-su2 build/arm64/sha256-su2-selftest
	./build/arm64/sha256-su2-selftest
	KEYHUNT_BIN=keyhunt-arm64-sha2-neon-su2 bash tests/arm64-smoke.sh
	KEYHUNT_BIN=keyhunt-arm64-sha2-neon-su2 python3 tests/arm64-vectors.py
	KEYHUNT_BIN=keyhunt-arm64-sha2-neon-su2 bash tests/arm64-solved-fixtures.sh

arm64-sha2-neon-su2-center-test: arm64-sha2-neon-su2 arm64-sha2-neon-su2-center
	KEYHUNT_BIN=keyhunt-arm64-sha2-neon-su2-center bash tests/arm64-smoke.sh
	KEYHUNT_BIN=keyhunt-arm64-sha2-neon-su2-center python3 tests/arm64-vectors.py
	KEYHUNT_BIN=keyhunt-arm64-sha2-neon-su2-center bash tests/arm64-solved-fixtures.sh
	python3 tests/arm64-center-compare.py
