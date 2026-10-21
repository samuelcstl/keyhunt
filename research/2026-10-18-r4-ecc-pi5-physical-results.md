# Physical Pi 5 R4 radix/NEON microkernel screen, 18 October 2026

## Verdict

**All cryptographic checks PASS. Every alternate kernel is slower than the
existing 4×64 scalar field multiplication in this short microbenchmark.
Do not integrate any current R4 implementation into the Keyhunt worker.**

**This rejects the current drop-in kernels, NOT arbitrary resident-limb
NEON field implementations or optimized libsecp256k1 backends.**

## Source and integrity

User-supplied `r4-ecc-results-20261018T160958Z-724580.tar.gz`;
archive SHA256:
`271e84c1a331274d6502d54414a38fc5c807a0bdcba7d01def7ee6b8d2404b1a`.

- SHA256SUMS 17/17 files validated; binary SHA matches the list.
- Run ID `20261018T160958Z-724580`, `run-status.txt` says `completed`
  with exit code zero.
- **Tested commit** `4011bfa885f8c4efa2d520bf6a618e22395279c9`.
- Physical 4-core Raspberry Pi 5, AArch64 Cortex-A76 @ 2.4 GHz,
  kernel `6.18.50+rpt-rpi-2712`, GCC 14.2.0.
- Temperature rose 48.8 to 51.0 C; no throttling (`0x0`).
- Background Bitcoin/altcoin daemon and pool processes were active but
  low individual CPU utilization. Reverse order and small within-variant
  spread help, but CPU affinity/isolation and independent repetitions
  were not controlled.

## Correctness

`make arm64-r4-ecc-test`: **PASS 20,484 field products** across
all six implementations, versus the previously independent Python-checked
4×64 native field (11×11×4 boundary products plus 5,000 random 4-way
batches). The test compares exact canonical 256-bit results, not only
low limbs. Historical 4×64 field backend has wider multiplication and
squaring tests, but these R4 prototypes have not been validated within
full key scanning.

## Microbench results (real Pi, 1 second × 2 reverse-order passages)

| Variant | Pass 1 mul/s | Pass 2 mul/s | Median mul/s | vs 4x64 |
| --- | ---: | ---: | ---: | ---: |
| 4x64 native | 15,648,686 | 15,645,490 | **15,647,088** | reference |
| 5x52 scalar | 10,622,453 | 10,608,954 | **10,615,704** | **-32.16%** |
| NEON 10x26 (2 lanes) | 6,529,713 | 6,526,136 | **6,527,925** | **-58.28%** |
| 10x26 scalar | 6,008,403 | 6,016,145 | **6,012,274** | **-61.58%** |
| 16x16 scalar | 3,493,295 | 3,495,145 | **3,494,220** | **-77.67%** |
| NEON 16x16 (4 lanes) | 2,815,332 | 2,814,135 | **2,814,734** | **-82.01%** |

Derived per-operation throughput reciprocals:
4x64 ~63.91 ns, 5x52 ~94.20 ns, 10x26 scalar ~166.33 ns,
NEON 10x26 ~153.19 ns, 16x16 scalar ~286.19 ns,
NEON 16x16 ~355.27 ns. These are **single-process average
batch throughput costs**, not a one-key ECC scan latency.

NEON 10x26 **+8.58% within its own 10x26 family**, yet still
2.40× slower than the native control. NEON 16x16 **-19.45%**
within its own 16x16 family. A larger SIMD lane count does not guarantee
faster modular arithmetic.

Within each candidate the two 1-second passes differ by <=0.13%,
supporting gross rejection but not sufficient to qualify small wins.

The benchmark updates input operands on every outer-loop iteration to
avoid loop-invariant multiplication removal by LTO. It includes full
radix unpack, convolution, carry normalization, pack, pseudo-Mersenne
reduction and canonicalization for each 4×64 output. The native baseline
already uses optimized 16-limb-product scalar MUL/UMULH and reduction.

## Machine code observations

Saved full linked AArch64 disassembly contains true SIMD:
`umull v31.2d`/`umlal v31.2d` for 2×32-bit lane multiplications,
and `umull v0.4s` for 4×16-bit lanes. Thus the NEON paths did compile
to vector multiply instructions. Output also contains scalar `umulh`
and `mul` from the optimized 4×64 backend and other scalar code.

This disassembly does **not** isolate PMU cycles per stage: no `perf stat`
or hot-symbol samples were collected in this quick run. We cannot yet
quantify what fraction of the NEON deficit comes from conversion,
carry chains, convolution, lane shuffles or scalar reduction.

## Why this is not an absolute radix ranking

- These 5x52, 10x26 and 16x16 kernels are **straightforward
  reference-style convolutions**, *not* the fully hand-optimized
  libsecp256k1 5x52 backend.
- The candidate kernels unpack all inputs from canonical 4x64,
  compute, then pack/reduce to canonical 4x64. A full ECC pipeline
  could retain an alternate limb representation across point
  arithmetic and batch inversion. Eliminating conversions can help,
  but does not alone prove that it closes a 32-82% performance gap.
- The 10x26 NEON kernel processes two independent products, and
  16x16 NEON four, but there is no persistent array-of-structures
  to structure-of-arrays (SoA) layout across points.
- No complete ECC point add, batch inverse, SHA256/HASH160, Keypool
  throughput is measured. **Do not label these as Mkeys/s.**

## Decision and next experiment

1. **Reject integration/promotion of these exact R4 drop-in kernels.**
   The sustained control is faster in all measurements, by wide margins.
2. Preserve their correctness fixtures and source as useful
   architecture evidence, not performance candidates.
3. If pursuing SIMD, test a narrowly scoped **resident-limb SoA
   10x26 two-lane** prototype as a **separate experiment**: count
   conversion/layout costs, implement reduction and normalization
   without round-tripping to 4x64 for each MUL, and verify complete
   chained operations (not one isolated product).
4. Consider the lower-risk alternative: tune the already fast 4x64
   `mul/umulh` dependency chains and pseudo-Mersenne fold
   (`reduce_k1` currently carries a dependent `while(carry)`
   loop), plus ILP between independent ECC points.
5. Continue **short 1–2 s × 2 reverse-order microbench screening**,
   archive on success/failure, then 15–30 s full worker A/B only if
   a candidate demonstrates a convincing local gain. Do not run
   multi-minute whole-worker benchmarks for rejected R4 candidates.

The evidence packager worked: archive, inner SHA256SUMS, build logs,
source, binary, disassembly, raw CSV, assessment and machine provenance
were all received and validated.
