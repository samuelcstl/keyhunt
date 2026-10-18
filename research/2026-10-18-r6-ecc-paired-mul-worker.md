# R6 short real-worker ECC paired native field multiplication validation

**Status: ARM64 correctness PASS; physical Pi 5 full-worker throughput
not measured; no production promotion or merge.**

R5 physical Pi isolated kernel screen (`r5-ecc-results-20261018T163146Z-777466.tar.gz`,
verified archive SHA256
`5361814388235fdc930ba628d8dedd79e31b2327a52138d3005c46b4b1becac5`)
showed 4×64 paired ILP +6.71% field MUL throughput and paired/first-fold
+7.53% versus the native R5 8-deep 2-independent-chain control.
The early-fold alone was +1.19%. These are *not* Keyhunt completed keys/s.
R5 resident-NEON 10×26 was -24.73% and not carried forward.

This R6 branch is stacked on R5, **only** changes the two affine slopes
`s_plus=(Gn.y-startP.y)*inv_dx` and
`s_minus=(-Gn.y-startP.y)*inv_dx` that are already independent in the
R3-scheduled point loop. Both numerator subtractions and batch inverse
remain unchanged, as do the R2 SRI RIPEMD160 and ARM hardware SHA256.

Three real compiled workers are compared:
- `keyhunt-worker-r3-ecc-sched` (untouched R3 SCHED control)
- `keyhunt-worker-r6-ecc-pair` (two interleaved 4×64 row products)
- `keyhunt-worker-r6-ecc-fold` (same, first fold unconditionally executed)

These workers are built separately. The default
`keyhunt-worker` and existing SQLite Puzzle 71 campaign are untouched.

## ARM64 correctness

[CI 39146189555](https://github.com/samuelcstl/keyhunt/actions/runs/39146189555)
passed:
- 51,000 distinct matched 2-way modular product triples (1,000 boundary,
  50,000 random), both candidate variants agree with `field_k1_arm64_mul`;
- known Puzzle #20 recovery in both standalone variants;
- 71-bit, 140-bit and 256-bit scalar/parity vectors;
- upstream solved fixtures;
- persistent four-thread worker JSON protocol;
- 524,288 exact distinct Puzzle20 candidate keys in 512 of 512 groups;
- bounded crash replay with no committed-chunk rehash.
All checked before any physical speed comparison.

## Pi5 short A/B, archived automatically

```bash
cd ~/BITCOIN_ANALYSIS/bitcoin-puzzle/keyhunt
git fetch origin experiment/pi5-r6-ecc-paired-mul-worker-20261018
git worktree add -b pi5-r6-ecc ../keyhunt-r6 \
  origin/experiment/pi5-r6-ecc-paired-mul-worker-20261018
cd ../keyhunt-r6
bash tests/arm64-r6-ecc-screen.sh
```

Default `KEYHUNT_R6_JOBS=32`, `KEYHUNT_R6_REPEATS=2`.
Each treatment completes 32 × 1,048,576 distinct synthetic test keys;
the real four-thread worker JSON protocol is exercised. Each candidate
runs directly paired with the control, in reverse order, twice. Approx
4–5 s per treatment at previously observed ~7Mkeys/s, **8 observations,
~35–45 s of active worker time**, plus build and correctness; not
minute-long 120-second standalone repeats. No production cursor moved.

Run, build, complete solved-puzzle tests, all workers and hashes,
full disassemblies, temperatures, OS process snapshots and raw worker
TSVs are automatically archived under:
`~/r6-ecc-results-<runid>.tar.gz`
and matching `.sha256`, even if an intermediate stage fails.

These four treatment pairs provide an initial **quick rejection or
shortlisting screen**, not a tight confidence interval. If the gain is
<1% or noisy, test more paired repeats before comparing on scratch
SQLite. Do not call a +7.5% field-MUL result a +7.5% Keyhunt result.

## Caution on frequency samples

R5 recorded 1.9 GHz before the short screen (idle) and 2.4 GHz after.
No per-variant clock data was captured; temperature 47.2–49.9°C and
`get_throttled=0x0` are favorable but do not prove fixed clocks.
R6 per-observation worker data records before/after clocks and thermal
status; use these to qualify the full-worker outcome.
