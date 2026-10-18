# R2 RIPEMD160: physical Pi 5 evidence review (2026-10-18)

**Status: machine-code and correctness PASS; throughput gain reproducible across the recorded samples; promotion deferred.**
The tested code came from commit `0e0fd1de1ebe12f5e0634280ccaa445449d30608`
on `pi5-r2-ripemd` tracking `experiment/pi5-ripemd-rotate-20261018`.
Runtime: Raspberry Pi 5 4x Cortex-A76 ~2.4 GHz, Debian
`6.18.50+rpt-rpi-2712`, GCC `14.2.0`, `-O3 -mcpu=cortex-a76 -flto`.

User-supplied raw archive: `r2-ripemd-results.tar.gz`;
SHA256 `e8c5a18cee94e3dbfa7199e27b0256ff89b4f6142e1cfc8192e423f8673661e4`.
Original folder: `runs/arm64-r2-ripemd/20261018T123905Z-212344`.
The archive's **54 SHA256SUMS entries verified successfully**. Raw archive
contains correctness logs, standalone and paired-worker TSVs, PMU files,
thermal samples and full disassembly. Do not add large raw artifacts to Git.

## Correctness

Both SLI and SRI passed all tests: 20,480 NEON four-lane target
comparisons versus full RIPEMD160 digests; recovered Puzzle #20 and upstream
solved fixtures; independent 71-/140-/256-bit ECC/parity vectors; persistent
worker protocol, no invalid jobs; exact 512 × 1024-key HASH160 groups
(524,288 distinct keys) and expected bounded crash replay. No FAIL,
ERROR or traceback in the archived test log. Persistent production Puzzle #71
database remained untouched.

## Sustained full-chain scalar-to-HASH160 benchmark

Four physical CPU cores, 120 s per trial, 2 interleaved reversed repetitions,
hardware `perf stat` and 10 s thermal samples. Each rate is completed scalar
candidate *attempts* in standalone `-R` mode, not distinct globally
checkpointed Keypool chunks.

| Variant | Repeat 1 keys/s | Repeat 2 keys/s | Median keys/s | vs R1 |
| --- | ---: | ---: | ---: | ---: |
| R1 baseline | 7,211,889 | 7,221,613 | **7,216,751** | reference |
| USHR+SLI | 7,345,062 | 7,342,302 | **7,343,682** | **+1.759%** |
| SHL+SRI | 7,347,289 | 7,364,242 | **7,355,766** | **+1.926%** |

The PMU-backed, approximate normalized per-candidate results:

| Variant | Cycles/key | Instructions/key | Branch misses/1000 keys |
| --- | ---: | ---: | ---: |
| R1 | 1,225.95 | 1,706.91 | 2,798.7 |
| SLI | 1,204.35 | 1,631.31 | 2,765.4 |
| SRI | 1,204.23 | 1,631.22 | 2,766.7 |

SRI vs R1: **-1.77% cycles/key**, **-4.43% instructions/key**.
Source harness extrapolates the last 5-second counters to the full PMU
window, so normalized per-key values are approximate. CPU user cycles
and wall Mkeys/s support the same directional change.

## Real persistent four-thread worker protocol (no SQLite)

Every observation completes exactly **268,435,456 distinct test keys** from
identical synthetic-seeded temporary jobs using the four-job JSON pipeline.
Each treatment alternates order by repetition.

| Treatment | Paired gain % by repetition | Median paired gain | Wins |
| --- | --- | ---: | ---: |
| SLI vs R1 | +2.908, +0.923, +1.028 | **+1.028%** | 3/3 |
| SRI vs R1 | +1.393, +0.602, +2.377 | **+1.393%** | 3/3 |

Six of six paired wins favor the rotation-optimized workers. Medians are
slightly lower and more variable than standalone 120s estimates. This
is a real process-protocol comparison but **not a complete persistent
SQLite Keypool throughput test**. The script's line reading "R1 vs control"
is a generic label even for this R2 candidate, not a comparison error.

## Codegen attribution from user Pi disassemblies

In the actual LTO-linked `GetHash160_fromXYParityTarget` function:

| Variant | A64 instructions | SHL | USHR | ORR | SLI | SRI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| R1 | 2168 | 344 | 325 | 332 | 0 | 0 |
| SLI | 1863 | 28 | 325 | 15 | 318 | 0 |
| SRI | 1863 | 344 | 9 | 15 | 0 | 318 |

**305 fewer linked A64 instructions** in the call site, a 14.07% static
reduction for *this function*, not for the whole engine. Since the function
hashes four compressed keys, this corresponds to ~76 instructions/key
if all paths traverse it. PMU independently observed ~75.7 fewer
instructions/key, a unusually strong mechanistic match to the codegen
hypothesis.

ECC `field_k1_arm64_mul` (148 instructions) and
`field_k1_arm64_square` (140 instructions) had **identical encoded
instruction sequences across all three binaries**. The separate SHA256
function's active instruction sequence is unchanged: it has a few
relocated `ADRP` encodings because binary layout changed, and the
control includes two trailing alignment NOPs absent in the variants.
Thus the significant instruction reduction is genuinely from RIPEMD160
rotation expression, not an accidental rewrite of ECC/SHA256.

## Measurement hygiene

Thermal probe ranges across all standalone variants 53.2–64.8°C;
all 72 sampled `get_throttled` observations `0x0` (12 per run).
ARM clock samples remained ~2.4 GHz. Cold control rose from 53.2 to
60.9°C; late control repeated at 61.5–64.8°C with comparable rate,
supporting thermal stability. However external node/pool contention
remains possible: no dedicated CPU isolation proven.

**SRI's lead over SLI is only ~0.165% in the standalone median**, below
the size of several trial-to-trial variations and comparing worker
treatments from distinct six-run campaigns. Treat SLI/SRI as
**equivalently qualified candidates**, not an established ranking.

## Recommendation

1. Keep both variants and the R1 baseline for machine-code forensics.
2. Carry the ROTATE-INSERT identity (SLI or SRI) forward as a **CPU
   optimization candidate**, because correctness, codegen, PMU and
   full worker rate all support improvement.
3. If choosing the best of SLI vs SRI matters, run a direct paired
   comparison **on the same Pi**:
   ```bash
   python3 tests/arm64-r1-worker-ab.py \
     --control keyhunt-worker-r2-ripemd-sli \
     --candidate keyhunt-worker-r2-ripemd-sri \
     --jobs 256 --repeats 6
   ```
   The script compares unchanged synthetic-seeded chunks, and never
   uses a production Keypool database.
4. Before production promotion, run the real SQLite Keypool A/B with an
   explicit experimental worker on a scratch DB, and finish parent
   PR #2 qualification; do not merge R2 independently of its parent.
5. Next high-value work remains ECC field MUL/reduction and inversion
   dataflow: ~69% of baseline CPU sampled time, versus ~21% in RIPEMD160
   and 8.5% in SHA256. Further RIPEMD160 gains are possible but bounded
   in end-to-end contribution by Amdahl's law.
