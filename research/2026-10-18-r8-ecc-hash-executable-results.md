# R8 implementation: real ECC producer to HASH160 consumer

**Working ARM64 experiment, not production or Keypool integration.**

PR #9 now includes an executable `tests/arm64-r8-ecc-hash-pipeline.cpp`.
It is not merely a plan: the producer performs the same secp256k1
affine point math as the Keyhunt 1024-candidate hot loop, while a separate
consumer calls the **actual 4-way SHA256 hardware + NEON RIPEMD160
target-comparison backend** from `Secp256K1`. They overlap through a
mutex/condition-variable bounded packet ring. Exact scalar key offsets
are carried for every packet, handling the mirrored plus/minus ordering.

## Producer

- Precomputes all 512 generator multiples once; retains the same
  generator and prime initialisation as the parent.
- Uses **one Montgomery batch inversion of 513 denominators per 1024
  candidates** through unchanged `IntGroup::ModInv()`.
- Uses a configurable **independent 4x64 field arithmetic width W =
  1/2/4/8/16**. For W>1, scheduling uses interleaved 64-bit products
  and carry chains across **2×W slopes**, then both X coordinates,
  then **2×W independent Y products**, not only 2 slope products.
- Computes the centre *incrementally* using the already inverted
  last denominator and a +1024G EC addition, rather than redoing scalar
  multiplication every 1024 keys.
- Emits canonical X + Y parity for four logical key offsets as soon
  as a quartet completes. Index packets are emitted **out of numeric
  scalar order**, and the four unfinished-quartet packetizer uses a
  small associative set, not a group-id modulo mapping (which collided
  at mirrored offset boundaries).

## Consumer and backpressure

- A second thread pops bounded 4-key packets (default depth 32),
  reconstructs the expected compressed pubkeys from X/parity, and calls
  `GetHash160_fromXYParityTarget`, the same optimized four-lane
  target-aware backend used by Keyhunt.
- Tracks actual **ECC produced keys** vs **HASH160 consumed and hashed
  keys**, verified Puzzle20 hits, queue-full waits on producer,
  queue-empty waits on consumer, and maximum queue occupancy.
- Full queue blocks producer, empty queue blocks consumer, and completion
  closes and drains the queue before reporting. No key is committed
  merely because the ECC stage completed.
- This implementation is **two threads, not automatically four**. A
  Pi5 four-core worker can run more independent instances, but choosing
  optimal CPU topology is a subsequent benchmark. Do not compare a
  two-thread pipeline directly with Keyhunt's four-core total Mkeys/s.

## Correctness proven on real AArch64 runner

[CI 39157070710](https://github.com/samuelcstl/keyhunt/actions/runs/39157070710)
passed for **all five widths**:
- 3 consecutive 1024-key batches each, including incremental center
  advancement; **3072 points per width** compared X and Y to
  independently scalar-multiplied `k*G`.
- **3072 compressed HASH160 digests per width** matched independent
  re-hashing of each scalar's public key, plus four-way target equality
  mask. One independently known Puzzle20 scalar was recovered.
- No duplicate/missing key index through packet assembly and consumer,
  including indices `0`, `512` and `1023`.
- The running consumer sees every packet exactly once, and the producer
  closes/drains its bounded ring successfully.
- Build, scripted physical evidence runner syntax, Python assessor and
  failure-safe archive tests passed.

A GitHub runner **0.2 s smoke**, W=4 and queue depth 8, confirmed
actual producer/consumer activity at ~3.21 million processed
HASH160/s on the runner, but **it is not a sustained or Pi5
performance result**. Do NOT infer a 4-core Mkeys/s improvement.

## First sustained physical Pi5 experiment

```bash
cd ~/BITCOIN_ANALYSIS/bitcoin-puzzle/keyhunt
git fetch origin experiment/pi5-r8-wide-ecc-pipeline-design-20261018
git worktree add -b pi5-r8-pipeline ../keyhunt-r8 \
  origin/experiment/pi5-r8-wide-ecc-pipeline-design-20261018
cd ../keyhunt-r8
bash tests/arm64-r8-pipeline-screen.sh
```

Defaults to **60 seconds per width**, 1,2,4,8,16, shared four-lane
HASH160 and queue depth 32, with full cryptographic proof up front.
`KEYHUNT_R8_PIPE_REPEATS=2` adds reversed-order replicates for
confidence; `KEYHUNT_R8_PIPE_QUEUE=8` tests a smaller ring.
This is a real pipeline throughput test with two OS threads, not a
synthetic isolated multiplier test.

Every invocation automatically creates a checksum-verified full
`$HOME/r8-pipeline-results-<run>.tar.gz` archive, even on failure,
containing source/build options/binary hashes, disassembly, full
correctness logs, per-width CSV, raw per-stage wait timers and Pi
sensors. **User can send archive without pasting terminal output.**

## Deliberate non-features

- No default worker or SQLite Keypool change; main unaffected.
- No coordinator, database-per-key, network, dedicated pinned CPU
  topology or unbounded queue.
- No claim that 15.5M field MUL/s equals double the 7.3M *four-core*
  completed key throughput. These units count different operations.
- No claim that width 16 is better than 8 or 4 before the 60-second
  physical width sweep. Register spills and extra memory traffic can
  outweigh the ILP benefit.

## Decision tree

If larger W increases ECC generated points/s and reduces consumer-empty
time, the arithmetic parallelism has become usable at the pipeline
boundary. If queue-full time rises instead, HASH160 needs more
independent consumers/cores or deeper downstream scheduling. If both
stay unchanged, profile the batch inverse dependency chain and the
compiled 4x64 product loops. Only move the proven code into a full
Keyhunt worker after sustained physical proof and a separate
four-core parity/coverage/crash-replay qualification.
