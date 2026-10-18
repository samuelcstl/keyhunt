# R6 physical Pi5 worker experiment: 18 October 2026

**Verdict: correctness PASS, experimental pair+fold worker has encouraging
but UNQUALIFIED +1.43% paired median (2/2 wins). Pair-only median -1.67%
(1/2 wins). No promotion, no production deployment.**

## Evidence provenance and integrity

User-provided `r6-ecc-results-20261018T170413Z-855883.tar.gz`
SHA256 `021a7691a91d6db70efb72b6085ca9358a7d309c105fe1bbd41e097992ba7e2c`.
Archived `SHA256SUMS` validated **36/36 files**, including exact ELF
worker binaries and ARM64 disassembly. Binary SHA256 values matched
`codegen/binaries.sha256`. Run status `completed`, exit code 0.

Tested commit `bab366cb736cc7a4555b1971c1b9a50d335a1ae3`;
physical Raspberry Pi 5 Cortex-A76 4 cores, 2.4 GHz reported,
GCC 14.2, kernel 6.18.50+rpt-rpi-2712.
Benchmark ran 17:04:13–17:05:55 UTC, with ambient nodes/pools
and background daemons running. CPU was NOT isolated.

## Correctness

- 51,000 field MUL2 differential vectors PASS, exact canonical output
- Known Puzzle #20 key recovered in both standalone variants
- Upstream fixture #1/#2/#3 and 71-/140-/256-bit scalar parity tests PASS
- Four-core JSON worker, invalid ranges and partition coverage PASS
- 64 disjoint Puzzle #20 chunks, 512 of 512 SHA256+RIPEMD160 groups
  and 524,288 distinct keys verified
- Correct bounded precommit crash/replay and no committed rehash
- Existing production Puzzle #71 database remained untouched

## Real worker 4-core throughput, identical synthetic scratch jobs

Each observation completes exactly **33,554,432 keys**,
32 × 1,048,576 jobs, ~4.6 seconds runtime. Reversed execution order
by pair; two pairs per treatment. The reference is R3-SCHED with
R2-SRI hashing.

| Pair/repeat | Reference Mkeys/s | Candidate Mkeys/s | Paired delta |
| --- | ---: | ---: | ---: |
| pair-only #1 | 7.330045 | 7.072297 | -3.516% |
| pair-only #2 | 7.258918 | 7.272138 | +0.182% |
| pair+fold #1 | 7.118013 | 7.264513 | +2.058% |
| pair+fold #2 | 7.176044 | 7.233685 | +0.803% |

- Pair-only median **-1.667%**, 1/2 wins. **Reject as a current performance winner.**
- Pair+fold median **+1.431%**, 2/2 wins. **Candidate for follow-up**, not qualified.
- The pair and fold sessions used different controls and were not directly
  paired. Never compare their raw medians as a treatment ranking.
- Reference performance drifted from 7.330 Mkeys/s at the start
  of the first session to 7.118 Mkeys/s at the start of the second:
  ~-2.89%, larger than the proposed +1.43%. System contention /
  short-window effects are a significant confounder.
- Temperature 53.2–60.4 C per observation; `throttled=0x0`
  at all before/after reads; sampled ARM clock ~2.4 GHz. Short
  before/after samples do not prove constant per-core frequency.
- No PMU cycles/instructions, `perf annotate`, energy or core
  occupancy time-series in this archive.

## Machine code

- Native `field_k1_arm64_mul` remains **148 instructions** in all
  3 actual worker disassemblies.
- Native `GetHash160_fromXYParityTarget` is **1,863 instructions**
  in all 3, demonstrating unchanged standalone hashing implementation.
- The pair and pair+fold helper functions are LTO-inlined. The
  static `thread_process` listing contains 6,040 A64 instructions
  in R3 SCHED, 6,056 pair-only and 6,025 pair+fold.
- All three thread_process listings include 188 MUL and 188 UMULH
  instructions *statically*. These do **not** imply equal dynamic
  instruction counts or latency, but support that no arithmetic
  product was skipped.

R5 microbenchmark: paired arithmetic showed +6.71% and
pair+fold +7.53% **field multiplication** throughput. R6 demonstrates
that the actual candidate-key worker gain is substantially smaller
and noisy. The hot function also performs square, batch inversion,
SHA256/RIPEMD160 and memory work.

## Decision and next validation

1. Keep R6 in draft; **pair-only is a negative trial** and should not
   be promoted on this evidence.
2. Spend one more SHORT, direct, reversed head-to-head on
   `keyhunt-worker-r3-ecc-sched` vs
   `keyhunt-worker-r6-ecc-fold`, for example
   64 jobs × four matched pairs, ~9 s per observation, about
   75 seconds active worker runtime. Skip repeating the long Puzzle20
   exhaustive test in *this* throughput-only follow-up, since the
   exact same worker build has already passed it. Archive binary
   hashes, logs, clock/temp and process status.
3. If all four paired effects remain positive and magnitude exceeds
   observed within-baseline drift, qualify separately with proper PMU
   cycles/instructions and a scratch SQLite full-pipeline trial.
   Otherwise reject/park this microoptimization and move to the
   much larger ECC batch inversion / field arithmetic path.
4. Do not alter default `keyhunt-worker`, the production database,
   main, or node/pool service defaults.
