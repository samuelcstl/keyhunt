# R8 physical Pi 5: sustained 60-second ECC→HASH160 width sweep (18 Oct 2026)

**Verdict:** The bounded two-thread streaming pipeline really works;
ECC W=16 processes **2.200M fully HASH160-consumed candidate keys/s**,
+9.92% against W=1 (2.002M) and +1.73% vs W=8. **Only one
60-second observation per width**; do not treat a modest advantage
over W=8 as statistically qualified.

Physical user-supplied file:
`r8-pipeline-results-20261018T191348Z-1183569.tar.gz`.
Full archive SHA256
`f0c160fcbbf78db564364254a952a404dca8f25ccea00a81c12a9b6f116eac58`.
All **34/34** in-archive SHA256 files validated.
Successful run `20261018T191348Z-1183569`, exit 0.
Tested commit `0b27ef9a2d6d8688af3cc28709fad66b899f90ec`.
Native Pi5 A76 with GCC 14.2, Linux 6.18.50+rpt-rpi-2712;
ARM sampled 2.400GHz; sensors 48.8C pre, 54.9C after
(52.7–56.5C during widths), throttled=0x0.
Background mining nodes and pools were running, no isolated CPUs.
Exact correctness PASS: all 3 consecutive 1024-key center-advance
batches per width, all X/Y vs independent scalar multiplication,
all HASH160 digests and target masks, exactly-once indexed
candidate packets, known Puzzle20 target hit.

## Physical 60s steady-state, one producer + one hash consumer

| W | Producer keys | Hash consumed keys | Actual HASH160 Mkeys/s | vs W1 |
|---:|---:|---:|---:|---:|
| 1 | 120,107,008 | 120,107,008 | **2.001767** | control |
| 2 | 113,698,816 | 113,698,816 | **1.894972** | -5.34% |
| 4 | 122,572,800 | 122,572,800 | **2.042867** | +2.05% |
| 8 | 129,781,760 | 129,781,760 | **2.163025** | +8.06% |
| 16 | 132,023,296 | 132,023,296 | **2.200378** | +9.92% |

Every observation ran ~60.000 seconds, queue bound **32 packets**.
Zero mismatches or lost results. All observations produced one
known target hit in the earliest batch.

## Per-batch physical-stage cost (1024 candidates)

Uninstrumented boundary and locking impact note below.

| W | Batch inverse, µs/batch | Point+packet+queue waits, µs/batch | Queue full waits, µs/batch | Hash active computed capacity, Mkeys/s |
|---:|---:|---:|---:|---:|
| 1 | 107.51 | 403.66 | 15.35 | 5.99 |
| 2 | 107.60 | 432.50 | 16.21 | 5.99 |
| 4 | 107.38 | 393.62 | 14.80 | 6.00 |
| 8 | 107.62 | 365.51 | 14.12 | 5.99 |
| 16 | 107.53 | 357.58 | 13.37 | 5.99 |

- The *same* serial `IntGroup` batch inverse costs ~**107.5 µs**
  per 1024-key group for all widths. Width W currently changes only
  paired slope/Y product scheduling and cannot speed this inverse.
- ECC X/Y producer (+ packet operations) becomes faster from **403.7**
  to **357.6 µs/batch** (11.4% lower at W16).
  Subtracting producer's measured full-queue wait gives approximately
  **388.3 to 344.2 µs/batch**, but this subtraction is NOT a
  perfect pure-X/Y metric (packet operations/locks still count).
- HASH160 primitive service time remains **~5.99 million digests/s
  per hash thread**, from actual HASH160 call time divided by
  keys, almost invariant with W. It is not the bottleneck.
- W16 consumer spends **22.0 seconds of 60s actively hashing**
  (~36.7%); approximately **30.2s** recorded waiting on the
  packet queue (~50.4%). W1 active ~33.4%, consumer waiting ~46.1%.
  There is additional bookkeeping/synchronization time outside
  HASH160 and queue.wait timers.
- Producer full-queue wait is **~1.7–1.8 seconds across 60s (~3%)**,
  compared with 26–30 seconds consumer-empty waits.
  So the **producer is the overwhelming bottleneck**. Intermittent
  queue-full waits do not imply hashes are saturated: they can
  occur during bursts of packets, while the consumer otherwise
  waits for the next batch's 513-element inversion.
- Queue max occupancy hits 32 for all widths, but that is only a
  burst peak, not evidence of sustained consumer backpressure.
  Current queue wait counters include uncontended predicate/lock
  bookkeeping, so they cannot be interpreted as exact OS-blocked
  fractions without a deeper wait-state trace.

## What the benchmark ACTUALLY tells us

R8 is a real **two-thread** producer/consumer concurrent pipeline,
**not** the existing 4-core ~7.3Mkeys/s worker. Replacing 4-core
production based on its 2.2Mkeys/s would be incorrect.
However a single ECC producer at W16 reaches only **~2.2M points/s**
while one hash consumer can sustain ~6.0M/s during active work.

**Next architecture experiment:** Keep the same bounded consumer,
add **2 or 3 independent ECC producers** with separate scalar ranges
and own batch centers (2 producer + 1 hash consumer = 3 threads;
3 + 1 = all 4 Pi cores), and/or test W32/W64. Measure
queue-full versus queue-empty and actual HASH160 target-verified
throughput at sustained 60s and repeated reversed runs.
Preserve an independent full-key indexing oracle and keyed searches
in the multi-producer version. Do not add external database
or network machinery in this phase.

If 3 producer cores approach >5.5M hashed/s but still trail the
7.3M 4-core baseline, revisit shared-core work scheduling and producer
efficiency; do not assume the streaming queues create arithmetic
speedups. Use native PMU to understand why the R8 point stage
is slower than R7 in-place point construction despite gaining from W.

**No production promotion** until the full 4-core end-to-end verified
key throughput exceeds the existing Keypool and all fixture/replay
invariants pass on Pi. Preserve this negative/positive mixed result
as physical evidence.
