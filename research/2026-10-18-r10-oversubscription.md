# R10: measure oversubscribed ECC/HASH160 on Pi5, independently of core count

**Status:** native ARM64 correctness PASS. Physical Pi5 throughput not measured.
Experimental only; no change to the Keypool production worker, the live
Puzzle71 SQLite cursor, or node/pool service defaults.

## Why R10 exists

Pi5 R8 physical 60s W16 with **one ECC producer and one HASH160 consumer**
completed ~2.200M exactly-indexed compressed HASH160 candidate keys/s,
while HASH160 primitive active capacity was ~5.99M/s and consumer
waited ~30s/minute for ECC points. This suggests allocating more compute
to ECC, but not necessarily pinning at most 4 software threads to 4 cores.

Cortex-A76 on Pi5 has **4 physical cores and no SMT**, so 6-12 CPU-bound
software threads cannot increase simultaneous arithmetic issue slots.
However oversubscription can sometimes reduce waste from bursts,
queue waits, synchronization and workload imbalance.
This is a benchmarkable hypothesis, not a claimed improvement.

## Actual executable

`tests/arm64-r10-oversub-pipeline.cpp` is a bounded multi-producer,
multi-consumer extension of R9's real ECC to HASH160 pipeline.

- Configurable `--producers 1..8` and `--consumers 1..4`;
  arithmetic ILP width `--width 1|2|4|8|16` remains independent.
- Every ECC producer owns its affine batch inverse, two-coordinate
  point generator, incrementally updated center and disjoint key range.
- Every HASH160 consumer owns its own secp256k1 context and uses the
  **real hardware SHA2 + NEON four-way RIPEMD160 target engine**.
- All threads use the same **bounded** MPMC queue; consumers race to
  pop whole four-key packets, with explicit scalar-key offsets.
- Correctness ledger is **shared across every hash consumer**, guarded
  during verification. It detects duplicates and missing keys even
  when packets are consumed out of order by different threads.
- Graceful shutdown closes the queue, wakes blocked producers AND
  consumers, and joins all threads before checking counters.
- The measured counters include total verified candidate keys consumed,
  actual active hash work, summed per-thread consumer-empty wait,
  producer-full wait and peak queue occupancy.
- Per-thread normalized busy / waiting percentages are used in
  `tests/arm64-r10-oversub-assess.py`, since aggregate idle
  seconds across 4 hash workers can exceed wall-clock seconds.

## Native ARM64 proof

[CI #39160444706](https://github.com/samuelcstl/keyhunt/actions/runs/39160444706)
passed all of:

| ECC producers | HASH160 consumers | Software threads | Independent points and hashes verified |
|---:|---:|---:|---:|
| 1 | 1 | 2 | 2,048 |
| 3 | 1 | 4 | 6,144 |
| 3 | 2 | 5 | 6,144 |
| 4 | 2 | 6 | 8,192 |
| 6 | 2 | 8 | 12,288 |
| 8 | 4 | 12 | 16,384 |

For each case, all X/Y coordinates matched independent scalar
multiplication, every compressed HASH160 digest matched the scalar
reference, all queued logical key IDs were present exactly once,
and the known Puzzle20 match was recovered correctly. Runner source,
archive script, Python CSV assessor and fail-safe SHA256 archiver pass.

The runner also did a **0.3-second smoke with four producers and
two hash consumers**. It showed that the concurrent pipeline runs
and drains without missing keys, but its throughput is **NOT**
physical Pi evidence and is too short for performance inference.

## Physical benchmark with reversed sustained observations

```bash
cd ~/BITCOIN_ANALYSIS/bitcoin-puzzle/keyhunt
git fetch origin experiment/pi5-r10-oversubscribed-pipeline-20261018
git worktree add -b pi5-r10-pipeline ../keyhunt-r10 \
  origin/experiment/pi5-r10-oversubscribed-pipeline-20261018
cd ../keyhunt-r10
bash tests/arm64-r10-oversub-screen.sh
```

Default is **60 seconds per configuration**, two rounds with
reversed order, seven configurations:

`1P/1H`, `3P/1H`, `3P/2H`, `4P/2H`,
`6P/2H`, `8P/2H`, `8P/4H`.

All use W16 and the same bounded queue depth 32. This is a meaningful
duration but involves 14 sustained observations; if only screening,
`KEYHUNT_R10_REPEATS=1` takes one 60s observation per configuration.
The script automatically archives exact source, compiled ELF and
disassembly, independent correctness results, per-configuration
complete CSV, thermal/clock samples and SHA256 checksums as
`~/r10-pipeline-results-<runid>.tar.gz`, even on failure.

## Engineering decision criterion

Do not choose the maximum thread count based on folklore. Prefer the
lowest-count configuration achieving **higher sustained verified
keys/s**, with stable temperatures and lower normalized consumer
starvation or producer backpressure across matched physical tests.
Extra software threads can improve overlap if significant blocking
or bursts exist; CPU-bound oversubscription can **lose** from context
switching, cache thrash and worse core contention.

A win in this experimental multi-thread engine is not yet a
production Keypool four-core speed win: keep the immutable R3
control, exact Puzzle20 coverage and crash/replay qualifications
before changing the real worker.
