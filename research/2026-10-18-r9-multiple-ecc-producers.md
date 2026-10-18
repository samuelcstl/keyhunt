# R9: scale independent ECC producers against the *same* 4-lane HASH160 consumer

**Status: native ARM64 correctness PASS, physical Pi5 throughput not yet
measured; experiment only.** R9 stacks on R8, and is not a production
Keyhunt / SQLite Keypool replacement.

## Why

Physical Pi5 R8 performed five real, 60-second observations with one
ECC producer and one real HASH160 consumer:

| Width W | 60s full HASH160 verified keys/s | vs W1 |
| ---: | ---: | ---: |
| 1 | 2.0018 M | baseline |
| 2 | 1.8950 M | -5.34% |
| 4 | 2.0429 M | +2.05% |
| 8 | 2.1630 M | +8.06% |
| 16 | **2.2004 M** | **+9.92%** |

Pi5 archive SHA256:
`f0c160fcbbf78db564364254a952a404dca8f25ccea00a81c12a9b6f116eac58`,
34/34 inner checksums verified. 1×W16 consumer actually
hashes only **~22s of its 60s** (~36.7%): its active 4-way hash
throughput is **~5.99M compressed HASH160/s**, but the ECC producer
supplies only **2.20M X/parity points/s**.

The inverse stays at 107.5 microseconds per batch at every width.
At W16, producer X/Y + packet/queue 357.6 microseconds per 1024,
and consumer queue-empty 30.2s per minute. The hash stage is
**undersupplied**, and periodic queue-full bursts (1.7s/min)
are not sustained hash saturation.

**We need to prove scaling on 4 cores, not conjecture that W=16 is
a full Keyhunt win.** Note W=2 uses a custom field kernel rather
than exactly the same scalar entrypoint as W=1; prefer W8 vs W16
comparisons when considering the ILP implementation itself.

## Executable R9 change

Reuse R8 full-affine, actual secp256k1 point generation, incremental
batch center and four-way SHA256/NEON RIPEMD160 target comparison.

- `--producers 1|2|3`: distinct ECC producer threads each maintain
  independent generator table, inverse batch and center state.
- Every producer gets a **disjoint uint64 scalar range separated by
  2^32** so no duplicate scalar can be produced by another source
  during the benchmark. Each batch emits exactly 1024 indexed
  X/parity keys, with explicit IDs through the packet queue.
- One shared bounded ring and **one** four-lane consumer; producer and
  consumer counts are separately captured. On producer/consumer
  errors, queue closes and notifies **both** blocked pushers and
  poppers; all threads are joined before rethrowing.
- Every source continues to use exactly **one** 513-denominator
  `IntGroup::ModInv` per 1024 keys.
- Two independent sources do NOT imply hash widths eight or sixteen;
  SIMD hash width stays four. W=1/8/16 determines the producer's
  independent 4x64 product scheduling within *each* source.
- Duration, queue depth and order of physical treatments are
  configurable; no production worker / SQLite cursor touched.

## Verified correctness

Native ARM64 [CI 39159476951](https://github.com/samuelcstl/keyhunt/actions/runs/39159476951)
passed all **3 producer counts x 3 widths**, with 2 batches/source.
For P=3, this validates 6144 points per width against independent
scalar multiplication, plus every compressed HASH160 and lane target
mask, proper index mapping in the shared queue, exactly once
consumption and Puzzle20 key recovery. All P1/P2/P3 tested.

The GitHub runner 0.25-second smoke showed **poor throughput**
under P3 and apparent producer queue stalls. It is short and runs
on an unknown shared vCPU topology: **not a Pi5 capacity result**.

## Physical Pi5 sustained test (not the 3-second mistake)

```bash
cd ~/BITCOIN_ANALYSIS/bitcoin-puzzle/keyhunt
git fetch origin experiment/pi5-r9-ecc-producer-scaling-20261018
git worktree add -b pi5-r9-pipeline ../keyhunt-r9 \
  origin/experiment/pi5-r9-ecc-producer-scaling-20261018
cd ../keyhunt-r9
bash tests/arm64-r9-pipeline-screen.sh
```

Five treatments, each **60 seconds** plus validation/build:
P1/W16, P2/W16, P3/W4, P3/W8, P3/W16. One hash
consumer throughout. This tests 2-, 3- and 4-thread CPU
allocation as well as ICC/ILP width, with queue capacity 32.
`KEYHUNT_R9_REPEATS=2` repeats treatments in reverse order.
Output automatically archived to
`$HOME/r9-pipeline-results-<runid>.tar.gz`, plus SHA256,
even if an intermediate operation exits unsuccessfully.

## Interpreting the outcome

If P3/W16 supplies ~6M+ points/s, the hash consumer should
approach its measured active ~6M capacity and producer queue-full
waits will increase. If P3/W16 remains much slower, then either
4-core contention, source memory traffic, packet synchronization
or the unoptimized 513-element batch inverse limits scaling.
Measure `producer_inverse_ms`, `producer_points_ms`,
`consumer_hash_ms`, `queue_full_ms`, `queue_empty_ms`.
The latter counters include lock/predicate overhead, not pure
kernel OS sleep time.

If P3/W16 reaches near hash saturation, **a single 4-way HASH
consumer becomes the next hardware bottleneck**. On shared
four-core Pi topology, adding a second hash thread reduces
ECC producer CPU resources; do not assume an automatic win.

R8 two-thread W16 = 2.2 M consumed keys/s; R3-SCHED
four-core completed worker ~7.3 M keys/s. These are
different workloads and scheduling models and **must not be
directly equated**. A matched full four-core Keyhunt/Keypool
A/B remains a separate promotion gate.
