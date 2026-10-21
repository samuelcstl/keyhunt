# Keyhunt Pi 5: GPU source audit and cost-model probes (2026-10-11)

## Scope and performance baseline
Workload: Bitcoin Puzzle #71 compressed P2PKH target, **one** HASH160 target,
1024-key ECC batch, exact Y parity, SHA256SU0/SU1 two-stream, NEON RIPEMD160,
native AArch64 4x64 row product and specialized square.

Physical Pi 5 end-to-end best measured **6,719,160 scalar candidates/s**
(4 threads). A profile of the same row/square family attributes exclusive
samples: field MUL 28.59%, NEON RIPEMD160 18.83%, hardware SHA256 6.79%,
Int::Neg 3.70%, XXH64 2.27%, and thread_process 33.90%. The latter is NOT
merely loop overhead: LTO/inlining folds arithmetic into it. No instruction
stall or memory-pressure conclusion follows from this symbol-only profile.

A later A/B candidate with mathematically identical 16-product Comba
columns is **slower**: 6,526,402/s 4-core, versus 6,719,160/s for the row
product. It does not use a new CPU instruction. Its column carry bookkeeping
and dependency chains can outweigh fewer partial writes on Cortex-A76.
Do not promote Comba.

## External primary-source comparison

- [brichard19/BitCrack: CudaKeySearchDevice.cu](https://github.com/brichard19/BitCrack/blob/master/CudaKeySearchDevice/CudaKeySearchDevice.cu):
  batches denominator products/inversion, advances stored affine points
  using a fixed incrementor, hashes the **actual Y parity** in
  `hashPublicKeyCompressed`, and uses a GPU target lookup. We already have
  batch inversion, sequential plus/minus point generation, and Y parity.
- [BitCrack secp256k1.cuh](https://github.com/brichard19/BitCrack/blob/master/cudaMath/secp256k1.cuh):
  GPU 8x32-bit field limbs and PTX carry instructions, versus our CPU
  4x64-bit limbs and MUL/UMULH. PTX and CUDA warp techniques do not
  automatically transfer to ARMv8-A.
- [FixedPaul/VanitySearch-Bitcrack GPUCompute.h](https://github.com/FixedPaul/VanitySearch-Bitcrack/blob/master/GPU/GPUCompute.h)
  and [GPUHash.h](https://github.com/FixedPaul/VanitySearch-Bitcrack/blob/master/GPU/GPUHash.h):
  affine/symmetric point search and compressed-public-key hashing.
  No source-backed evidence here of a breakthrough beyond the algorithms
  we have adapted; published GPU throughput is not a Pi 5 speed predictor.
- [ipsbruno3/secp256k1-gpu-accelerator opencl/main.cl](https://github.com/ipsbruno3/secp256k1-gpu-accelerator/blob/main/opencl/main.cl):
  includes Jacobian point/scalar operations and sequential kernel, but its
  OpenCL source has **no SHA256/RIPEMD160 HASH160 address-check pipeline**.
  Its claimed GPU ops/s are therefore not comparable to our fully checked
  Bitcoin-address candidates/s.
- [Firsttime13/Keyhunt-Cyclone keyhunt.c](https://github.com/Firsttime13/Keyhunt-Cyclone/blob/main/keyhunt.c):
  recent CPU keyhunter fork advertises three-tier Bloom and direct RMD160
  search, but those are primarily multi-target/BSGS or address-format
  distinctions. Our MODE_ADDRESS and MODE_RMD160 already share the same
  20-byte HASH160 matching path, and the current single-target puzzle should
  not pay Bloom/XXH64 overhead.

## Avoidable operations visible in our source

### A. Point X arithmetic
At the 1024-point group hot loop, both P+iG and P-iG compute
`X3 = s^2 - Xcenter - Xgenerator mod p` by:
  1. `x.ModNeg()` => `p - x`
  2. `x.ModAdd(s_squared)`
  3. `x.ModSub(x_generator)`

The algebraically equivalent sequence is
`x.ModSub(s_squared, &x); x.ModSub(x_generator)`,
saving the modular negation/add combination. Benchmark as
`KEYHUNT_POINT_ALGEBRA`; preserve existing kernel as control and cross-check
full 71/140/256-bit keys. This tests an **avoidable operation**, unlike
further reordering of 16 multiply partial products.

### B. One-target HASH160 lookup
A single target has no need for probabilistic rejection. Existing path:
`bloom_check` (including XXH64) followed by binary search when positive.
For `N == 1`, direct 20-byte equality with `addressTable[0].value`
provides exact matching and removes hash/memory probes.
`KEYHUNT_SINGLE_TARGET_DIRECT` uses the direct path for one target and
preserves Bloom/binary search for `N > 1`.

### C. Other candidates, evidence still required
- Register/data movement: `Point pts[1024]` and `pp/pn=startP` copies;
  quantify with PMU instructions, data-cache misses, and disassembly.
- RIPEMD160 SHA-to-RIPEMD byte swaps/transposes: ~19% of exclusive samples;
  fusion may be worth it after A/B proof, but could increase register pressure.
- Long-term: change field limb representation (5x52, e.g. libsecp256k1),
  or 2-step curve formula changes. This is a much larger, riskier change.
- Endomorphism creates mapped scalars outside the Puzzle #71 bounded
  interval in general; never claim that its 3x/6x hash candidates mean the
  same increase in valid in-range scalar coverage.
- Distinct **scanned** scalar attempts/sec is not exact global unique
  coverage when random chunk selection overlaps. Checkpointing/disjoint
  chunk assignment matters for production lottery runs.

## Deeper measurement
1. End-to-end A/B in alternating order, >=2 repetitions at 1 and 4 cores,
   identical input target, same binaries, monitor thermals and throttling.
2. Use PMU `cycles, instructions, branches, branch-misses` to distinguish
   instruction count vs branch control vs hardware cost; hardware counters
   depend on kernel permissions and PMU availability. Lower cycles/candidate,
   not lower exclusive samples alone, is the objective.
3. Capture stack traces and instruction-level `perf annotate`, including
   the inlined code inside `thread_process` and MUL hot loops.
4. Evaluate changes using actual candidates/s and recovered-key invariants;
   only then profile the winner again.

Scripts: `tests/arm64-work-elimination-bench.sh` and
`tests/arm64-deep-profile.sh`. Three test variants plus the proven native
row-MUL+SQR control are retained as independently benchmarkable binaries.
