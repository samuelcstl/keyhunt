# Physical Pi 5 R3 ECC paired/NEON audit: 18 October 2026

**Verdict: PASS correctness, +1.43% standalone NEON, +0.79% standalone SCHED;
real worker SCHED repeatably positive in 3 of 3 paired measurements, NEON
unqualified with 2/3 positive. Do not merge or promote.**

## Source, reproducibility, files

Physical user-provided archive `r3-ecc-results-20261018T151336Z-587641.tar.gz`,
SHA256 **`124b785ed72f547e6b3fec84bb541c06497f95f4a66267fffa8c70b3e862a763`**.
57 file entries in the inner `SHA256SUMS` verified **57/57**. 
Run folder: `runs/arm64-r3-ecc/20261018T151336Z-587641`.
Tested Git commit **`44078f735f6ed8c9ad6b0e643f98d299c748f1d7`**;
the later automatic archive patch was not present during this physical run.
Compiler GCC 14.2.0, `-O3 -mcpu=cortex-a76 -flto`,
Linux `6.18.50+rpt-rpi-2712`, Cortex-A76 × 4, ~2.4 GHz.

No default worker or existing persistent Puzzle #71 SQLite campaign modified.
The source run archived the six full ARM64 objdump disassemblies,
per-binary SHA256 *lists*, but not the executable binaries themselves;
future runs now archive binary contents.

## Correctness

- 53,854 NEON dual-lane modular subtraction cases PASS.
- Known Puzzle #20 key recovered in both ECC variants; high-scalar
  and 71/140/256-bit parity fixtures PASS.
- Upstream solved fixtures PASS.
- Four-core persistent JSON worker protocol, invalid-range rejection PASS.
- Independent 64 disjoint and randomized Puzzle #20 chunks,
  all 512 `SHA256+RIPEMD160` groups covering 524,288 distinct keys PASS.
- Bounded crash replay, durable cursor correctness, no uncommitted gaps PASS.
- All 57 archived SHA256SUMS entries PASS.

## Standalone benchmark: complete ECC -> SHA256 -> RIPEMD160

Six full process runs, 4 physical cores, two 120-second periods per variant,
forward and reverse order; PMU perf stat.

| Variant | Run1 keys/s | Run2 keys/s | Median keys/s | Relative to R2-SRI |
| --- | ---: | ---: | ---: | ---: |
| R2-SRI control | 7,302,633 | 7,330,878 | 7,316,756 | reference |
| R3 SCHED | 7,361,206 | 7,387,839 | 7,374,523 | **+0.790%** |
| R3 NEON | 7,424,934 | 7,417,312 | 7,421,123 | **+1.426%** |

PMU counters normalized by **estimated** whole-window candidate counts.
The 5-second counter extrapolation makes them approximate.

| Variant | cycles/key | instructions/key | branch misses / 1000 keys | branches / 1000 keys |
| --- | ---: | ---: | ---: | ---: |
| R2-SRI | 1205.44 | 1632.55 | 2767.95 | 61,888 |
| R3 SCHED | 1199.26 | 1639.41 | 2835.99 | 61,378 |
| R3 NEON | 1194.55 | 1638.56 | 2572.70 | 56,386 |

NEON relative to R2: **-0.904% cycles/key**, **+0.369% instructions/key**,
**-7.05% mispredicted branches per key**, **-8.89% total branches/key**.
SCHED relative to R2: -0.512% cycles/key, +0.420% instructions/key,
+2.46% branch misses/key. These numbers **do not** prove the change
is limited by branch prediction, but demonstrate that NEON improvement
is not merely 'fewer instructions'.

All recorded `vcgencmd get_throttled` readings were `0x0`;
clock sampling is ~2.4 GHz. Post-warmup temperatures ~60-65°C,
no significant drift in NEON repeats. Background task contention remains
uncontrolled.

## Real four-core JSON worker: 268,435,456 completed key candidates/run

Reverse-ordered 3 paired trials per candidate, same synthetic-seeded
disjoint key chunks, **not SQLite Keypool service**.

| Pair / repeat | R2 control Mkeys/s | R3 Mkeys/s | Relative |
| --- | ---: | ---: | ---: |
| SCHED 1 | 7.336744 | 7.350042 | +0.181% |
| SCHED 2 | 7.321837 | 7.420854 | +1.352% |
| SCHED 3 | 7.322293 | 7.378961 | +0.774% |
| NEON 1 | 7.252331 | 7.409320 | +2.165% |
| NEON 2 | 7.371501 | 7.362952 | **-0.116%** |
| NEON 3 | 7.299278 | 7.316166 | +0.231% |

SCHED median paired **+0.774% (3/3 wins)**.
NEON median paired **+0.231% (2/3 wins)**.
The workers' R2 control rates differ across the two campaigns; comparing
SCHED to NEON as though they had been directly paired would be invalid.
Three trials per variant are insufficient to establish a stable small gain.
The standalone +1.43% NEON cannot be transported to a production +1.43%
claim without stronger worker evidence.

## Actual ARM64 machine-code inspection

`field_k1_arm64_mul` and `field_k1_arm64_square` have **identical
instruction opcode sequences** across all three standalone and all three
worker binaries in the saved disassembly. The R3 changes do not speed
up the 64x64->128 secp256k1 multiplication microkernel.

Both R3 variants change the LTO-generated `thread_process` body.
The standalone control's compiled `thread_process` has 5668
instructions (static listing), versus 5759 SCHED and 5767 NEON.
In worker form the listings are 6149 (R2), 6033 (SCHED), 6098 (NEON).
These static counts reflect compiler layout/inlining/branches, **not**
dynamic instruction counts and are not normalized per key.

The NEON path visibly contains the 64-bit vector compare/arithmetic
instructions `CMHI`, `CMEQ`, and lane-selection/mask ops, consistent
with the expected modular-subtraction implementation.
The HASH160 assembly routine remains 1863 instructions in all three
standalone binaries; encoded addresses differ with layout, but its
algorithmic source and objects are unchanged.

The extra NEON work applies only to the *paired slope numerator modular
subtractions*, leaving multiplications, squares and batched inverse scalar.
This limits the maximum current R3 SIMD return.

## Next decision

**Keep both R3 variants experimental.** SCHED is less noisy in the recorded
real-worker trials, while NEON has the best sustained standalone rate.
Do not conclude which is best in production from cross-campaign medians.

Do a direct `keyhunt-worker-r3-ecc-sched` versus
`keyhunt-worker-r3-ecc-neon` A/B with at least 6 reverse-order paired
repetitions, fresh synthetic disjoint same chunks and full archive. If the
difference remains <=0.5%, isolate CPU interference and repeat with
4-core affinity under a consistent configuration; only after that compare
on scratch SQLite campaign.

### Strategic ECC next round

The profile still points at field multiplication (including batched
inversion), affine point generation and carry/reduction dependencies.
Cortex-A76 NEON cannot do 64x64->128 *vector* limb products, so a
further NEON boost requires rethinking limb representation (e.g. 8x32
with 32x32->64 `UMULL`), or finding profitable independent chains
across multiple fields. Benchmark 4x64 `MUL/UMULH` baseline against
any 32-bit SIMD kernel with identical alias/canonicality oracles and
real completed worker keys/s. Avoid assuming SIMD provides a free 2×
speedup. Do not change parent PRs or enable any services.
