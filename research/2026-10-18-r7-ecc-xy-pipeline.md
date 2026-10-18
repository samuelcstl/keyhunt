# R7: conserve ECC point-pair independence through X **and** Y

**Status: experimental; ARM64 correctness under validation; Pi throughput not measured.**
No production Keypool/SQLite worker, fork, or service is affected.

## Why R6 failed the throughput test, what it does NOT prove

R5 established paired 4×64 8-deep **field multiplications** at +6.7–7.5%
in a controlled Pi screen. R6 replaced only the pair of initial
`slope = delta_y * inverse(delta_x)` products inside each affine
point-generation iteration. Full 4-core worker fell **-1.88% on four
paired follow-up comparisons**. This is a valid negative result for
*that integration*, not for all scheduling across two points.

Actual pre-R7 sequence after the slope pair:

```
s+ and s-                  independent
s+^2 and s-^2              independent
x+                         sequential
y+ = (Gn.x - x+) * s+ - Gn.y
x-                         sequential
y- = (Gn.x - x-) * s- + Gn.y
append points into pts[1024]
...
HASH160+comparison operates in 4-lane blocks after all points are ready
```

The paired multiplication's independent ILP chain ended when the plus
point's Y was finished ahead of the minus point's X. The compiler's
register pressure and instruction scheduler may also matter; **the
R6 regression does not establish the cause**.

## Three controlled variants against immutable R3-SCHED

- `keyhunt-worker-r7-ecc-sched`: no custom field multiplier.
  Compute both X coordinates before computing both Y coordinates.
  Leaves field operations scalar, to isolate instruction scheduling.
- `keyhunt-worker-r7-ecc-pair`: same grouped X/Y schedule; paired
  4×64 ILP kernel for BOTH the two slopes and the two Y products,
  with different independent operands for each Y operation.
- `keyhunt-worker-r7-ecc-fold`: same, with first-fold specialization
  for both slope and Y product pairs.

The independent multiplication helper now takes four input field
elements: `a0*b0` and `a1*b1`, unlike R6's shared denominator.
The old shared-denominator helper remains available. Both operations
return fully reduced/canonical results. Output buffers must not
alias inputs, ensured by separate point/temporary objects.

**Critical correctness detail:** The original R3 uses
`_s.Set(&ecc_minus_s)` when processing P- after P+. R7 deliberately
does NOT overwrite `_s` at that point, because it still needs the
original plus slope for the later plus Y. This was caught during
source review before correctness qualification.

The parity/Puzzle#71 path requires `calculate_y=true`.
R7 retains the same 1024-point memory ordering and the existing
four-lane SHA256/RIPEMD160/HASH160 target comparison; the hash backend
and result provenance cannot be changed by this experiment.
The full HASH160 stage still follows point generation as a group.
A future streaming hash implementation would need an independent
key-index mapping and exhaustive audit; **not slipped into R7**.

## Measure pipeline, not just Mkeys/s

The R7 candidates collect wall-clock stage counters per worker,
aggregated in `stages.tsv`:
- `inverse`: all input `dx` subtraction and batch `grp->ModInv()`,
- `point_xy`: all 1024 point coordinates, including special boundaries
  and optional endomorphism and center,
- `hash_scan`: all 4-lane hashing, comparisons and key bookkeeping.

Stage counters are monotonic clock durations summed across worker
threads; they show **relative stage share** and should not be mistaken
for process wall clock, CPU cycles or PMU counts. One-time scalar
center computation and next-center advancement are outside these
three timed sections.

These counters **diagnose** downstream bottlenecks but do NOT
demonstrate that the R6 regression was caused by the serial Y path.

## Fast Pi test with archives

```bash
cd ~/BITCOIN_ANALYSIS/bitcoin-puzzle/keyhunt
git fetch origin experiment/pi5-r7-ecc-pipeline-20261018
git worktree add -b pi5-r7-ecc ../keyhunt-r7 \
  origin/experiment/pi5-r7-ecc-pipeline-20261018
cd ../keyhunt-r7
bash tests/arm64-r7-ecc-screen.sh
```

- Build separately named binaries; default live Keypool worker untouched.
- Correctness: independent four-operand field MUL oracle, Puzzle20
  solved fixtures, scalar/parity target vectors, worker JSON protocol,
  524,288 distinct Puzzle20 keys and exact bounded crash replay.
- Default real four-core scratch worker A/B:
  24 × 2^20 keys per observation, 2 reverse-order repeats per candidate,
  R3 control compared with R7 SCHED, R7 PAIR and R7 FOLD.
  Roughly 40–60 seconds of *active worker timing*, depending on load,
  with separate tests/build outside that duration.
- `KEYHUNT_R7_JOBS=16` for an even shorter coarse screen,
  `KEYHUNT_R7_REPEATS=3` for a less noisy follow-up.
  Every treatment gets the same deterministic synthetic key chunks.
- On normal exit and errors: `~/r7-ecc-results-<runid>.tar.gz` and
  matching SHA256, entire source, ELF workers, disassembly, stage logs,
  performance runs, environment and correctness provenance.

This branch is **stacked on R6 solely for code reuse**. R6 itself
failed real-worker qualification and should not be merged.
If R7 wins, rebase the clean standalone R7 changes on the
last suitable R3/R2 parent rather than bringing the R6 experiment along.

## Next decision

If R7 improves stage `point_xy` and sustained *completed keys/s*
relative to R3, explore 4-point interleaving or coordinating the
already-4-lane hash pipeline. If stage `point_xy` improves but full
Mkeys/s does not, inspect the measured `hash_scan` share and
memory layout. If both remain flat/negative, focus on batch inversion's
prefix and suffix dependency chains before expanding SIMD.
