# Pi 5 CPU R1: correct-code-first, instruction-level qualification

Status: **unqualified candidate**, isolated from production.
Parent branch: `perf/pi5-arm64`, [baseline handoff](../docs/AGENT_HANDOFF_PUZZLE71_PI5.md).
R1 branch: `experiment/pi5-cpu-r1-evidence-20261018`.
**No measured R1 speedup is claimed. No Keypool campaign or service changed.**

## Why and what we reused

The SHA256d engine's [CPU research workbench](https://github.com/samuelcstl/btc-sha256d-engine/blob/main/research/cpu/WORKBENCH.md)
is our measurement model: exact source/binary/compiler identity, actual disassembly,
wall time plus CPU PMU cycles/instructions/stalls, balanced A/B observations,
thermal/frequency/throttle quality, and immutable evidence receipts.

Keyhunt already includes the earlier engine-derived two-stream ARM SHA256SU0/SU1
implementation, NEON RIPEMD160 and an A76-specialized secp256k1 4x64 field MUL/SQR.
SHA256d's related-header pre192-WK and nonce-specific midstate are not valid
drop-in optimizations for HASH160 of changing compressed pubkeys.

Baseline on physical Pi, 2026-10-14:
- 4-core standalone: **7.342 Mkeys/s**
- direct persistent worker: **7.336 Mkeys/s**
- durable SQLite Keypool: **7.291 Mkeys/s** (99.3% of standalone)
These are full parity-correct scalar-to-HASH160 candidates, not SHA256d hashes.
**Current baseline, not a theoretical limit.**

## Changes, each independently selectable

The `keyhunt.cpp` changes apply ONLY under new R1 macros:

| Build | Flag | Exact transformation |
| --- | --- | --- |
| `keyhunt-r1-stride4` | `KEYHUNT_R1_STRIDE4` | Compute `4*stride` once per thread rather than once per 4 keys. Supports arbitrary stride values. |
| `keyhunt-r1-neg-y` | `KEYHUNT_R1_NEG_GN_Y` | Precompute `-Gn[i].y (mod p)` for the immutable table, use exactly the old modulo-subtract. |
| `keyhunt-r1-zero-mask` | `KEYHUNT_R1_ZERO_MASK` | Skip the 4 scalar hit-check iterations if the exact NEON four-lane target mask is zero. Does not skip hashing or key advancement. |
| `keyhunt-r1-all` | all three | Combination, separately attributed. |
| `keyhunt-worker-r1` | all three plus existing worker flags | Same worker protocol, ranges, queue and completion accounting as `keyhunt-worker`. |

The original `keyhunt-worker` and NEON standalone control retain all their
existing compile flags and semantics. No controller/database edits or service
activation. R1 binaries link the exact existing ECC, SHA and NEON objects.

## Compile-time correctness gate

From the experimental branch only:

```bash
make arm64-r1
make arm64-r1-test
```

For each standalone variant: known Puzzle #20 solution, independent Python
71/140/256-bit parity/curve vectors, solved fixtures. The experimental worker
also re-runs the real four-thread protocol / known hit and the exhaustive
Puzzle #20 **post-HASH160** coverage/recovery test with
`KEYHUNT_WORKER_BIN=keyhunt-worker-r1`. Test default remains the original worker.

Failures block benchmarking and promotion.

## Pi benchmark + machine-code audit

The orchestrator will build/test, save the source and Makefile, SHA256 every binary,
save full `objdump -drwC` disassembly, preserve compiler versions/optimizer
defaults, run the existing balanced physical Pi PMU/sustained test for baseline,
individual R1 flags and combined R1, and run a **paired real-worker test**
on identical synthetic-seeded, nonoverlapping Puzzle #71 chunks:

```bash
KEYHUNT_R1_SECONDS=120 KEYHUNT_R1_REPEATS=2 \
  KEYHUNT_R1_THREADS=4 KEYHUNT_R1_PERF=1 \
  bash tests/arm64-r1-evidence.sh
```

Outputs go to `../runs/arm64-r1/<UTC-id>/`, outside Git. R1 standalone
observations use the historical `arm64-neon-target-bench.sh` physical protocol,
including `perf stat -x` cycles/instructions/branches/branch-misses,
5-second rate snapshots, and 10-second clock/temp/throttle snapshots.
`arm64-r1-worker-ab.py` measures true completed, disjoint full candidates over
elapsed wall time, with a separate scratch directory per treatment and reversed
A/B order by repetition.

Optional deeper instruction-level profiling (with independent unprofiled
winner selection) uses existing `arm64-deep-profile.sh`:

```bash
KEYHUNT_R1_PROFILE=1 bash tests/arm64-r1-evidence.sh
```

The deep profiler uses `perf record` call graphs, `perf report`,
`perf annotate` for the ECC kernel and inlined scan, and a software-clock
fallback when required. The raw executable disassemblies remain available even
if perf counters are permission-limited.

### Interpret measurements correctly

- Confirm `SHA256H/H2`, `SHA256SU0/SU1`, A76 `mul/umulh`, LTO and actual
  hot-loop instruction paths in the disassembly. **Inspect the compiler output**
  before asserting a source-level operation was removed.
- Compare absolute **cycles/key**, instructions/key, branch-misses/key, real wall
  candidates/s, frequency and stalled-cycle/cache evidence where available.
- The historical 5-second standalone reporting cadence makes PMU/key normalization
  **approximate** (full-window extrapolation). The separate worker completed-count
  timing is the throughput truth.
- Hardware counters, `perf record` and instrumentation perturb timing.
  Unprofiled, paired wall benchmarks remain performance acceptance authority.
- Source-level reductions can lose on Cortex-A76 from new dependencies, register
  pressure, cache traffic or lowered compiler optimization. Preserve every
  negative result. Inspect object/codegen of any close call.
- No fixed power-efficiency claim from PMU cycles. Measure actual wall power
  for joules/key if energy efficiency becomes a release criterion.
- Check present throttle bits and newly latched bits, clock/temperature drift,
  external CPU load and CPU occupancy, as in the SHA256d harness.

For quick **diagnostics only**:
```bash
KEYHUNT_R1_SECONDS=30 KEYHUNT_R1_REPEATS=2 \
KEYHUNT_R1_PERF=0 KEYHUNT_R1_WORKER_JOBS=32 \
  bash tests/arm64-r1-evidence.sh
```
This quick run cannot support a production speedup claim.

## Acceptance / next research

1. **Correctness**: every independent flag and combined worker passes tests,
   no missing/duplicated post-hash scalar coverage, identical hit handling.
2. **Quality**: sustained Pi paired runs have stable clocks/thermals, no active
   throttling/interference, successful perf access or explicit unavailability;
   preserve every sample, especially negatives.
3. **Performance**: repeated paired median improvement in measured keys/s
   exceeds run-to-run noise, direction supported by cycles/key and machine-code
   evidence. No arbitrary 5% gate for microoptimizations.
4. **Production**: only after qualification, explicitly decide whether to
   promote R1; rerun full Keypool benchmark and crash/reboot gates. No auto-merge,
   no default worker swap.

**Deferred:** branchless modular reduction/subtraction, compact XY layout,
SHA256->RIPEMD160 fusion, new ECC formulas and QPU kernels. Measure instruction-
level hot spots after R1 instead of predicting a win from source alone.
