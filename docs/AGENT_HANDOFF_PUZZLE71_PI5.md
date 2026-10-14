# Agent handoff: Pi 5 Bitcoin Puzzle #71 Keyhunt

**Updated:** 2026-10-13 (Europe/Paris)  
**Working branch:** `perf/pi5-arm64` in [samuelcstl/keyhunt](https://github.com/samuelcstl/keyhunt), [PR #1](https://github.com/samuelcstl/keyhunt/pull/1). **Do not merge to `main` without user approval.**  
**Last source snapshot before this handoff:** `d2a5a30d5ca1c88caad279f34bffd3acc4eb5761`; use `git rev-parse HEAD` for actual current head.  
**Upstream:** [AlbertoBSD/keyhunt](https://github.com/albertobsd/keyhunt), main branch. The substantial ARM64 search changes and benchmarks are in this fork, not upstream.  
**Primary goal:** efficient, *correct* compressed P2PKH HASH160 brute-force scanning of **BTC Puzzle #71**, with unknown public key, on a physical Raspberry Pi 5 (four ARM Cortex-A76 cores). The user's target file on Pi is `~/BITCOIN_ANALYSIS/bitcoin-puzzle/runs/bench71/target.txt` and currently contains the single target address. Don't change the target, scan unrelated keys, claim block-mining hardware helps, or confuse pubkey-known ECDLP rates with full HASH160 checks.

## Read these documents first

1. **[Upstream modes and search-space audit](../research/2026-10-11-keyhunt-modes-and-search-space.md)**: verified CLI semantics, applicability of modes/options, #71 mathematical range, randomness/overlap and prioritised coverage tests.
2. **[Pi5 architectural audit](../research/2026-10-11-pi5-architectural-audit.md)**: current code review of redundant stride multiplications, generator-Y negations, zero-match per-lane loops, cache/branch questions.
3. **[Production search KISS v1 spec](PRODUCTION_SEARCH_POLICY.md)**: one local controller and persistent worker; 2^50 disjoint scrambled chunks, one SQLite ordinal, bounded crash replay and minimal tests. Keep distributed-pool complexity outside v1.
4. **[GPU code comparison](../research/2026-10-11-gpu-source-audit.md)**: what transferred from CUDA implementations and what remains GPU-specific.
5. Upstream [README](../README.md), [Makefile](../Makefile), [keyhunt.cpp](../keyhunt.cpp), [SHA2 backend](../hash/hash4_arm_sha2_su2.cpp), [NEON RIPEMD160](../hash/ripemd160_neon4.cpp), [AArch64 field kernel](../secp256k1/field_k1_arm64.cpp). The upstream README is general-purpose and may describe **different performance metrics** or retired options; trust current source and tests for this branch.

## Production Keypool KISS v1 (new, experimental)

- Implemented in this PR: `keyhunt-worker` (four continuous NEON hashing threads, bounded four-job queue and asynchronous ordered result reporting), `pool/keypoold.py` (one locally locked SQLite campaign, seeded Feistel 50-bit permutation and up to four prefetched 2^20-key jobs), `pool/README.md` (manual test/runbook), optional disabled user-service template.
- GitHub Actions worker-and-pool job on commit `0a46f35394e793f724e67b78fa4312756d85f48c` **passed** worker unit/protocol tests, fake-worker crash replay, and real worker/controller four-job integration with SQLite resume across sessions.
- On Pi, validate with `make arm64-worker-test && python3 tests/keypool-controller.py && python3 tests/keypool-integration.py`. No service installation or auto-start. First real campaign run, once user approves and checks puzzle status: `python3 pool/keypoold.py init`, then `python3 pool/keypoold.py run --max-jobs 8`. Maintain low priority and record logs.
- Still pending: independent physical Pi sustained hash-rate comparison, kill/reboot fault injection and prolonged stability. Do not claim production readiness or full scalar-level coverage proofs from unit tests alone; do not merge to main without authorization.
- This KISS v1 uses single-machine trust and one acknowledgement cursor; it does not implement remote worker proofs, public pool or reward distribution.

## 2026-10-14: Pi 5 sustained four-job pipeline benchmark PASS

- Physical Pi 5 uncontended run: `nice -n 15 python3 tests/keypool-performance-ab.py --jobs 512 --baseline-seconds 60 --repeats 2 --cooldown 10`. Run records on Pi only: `runs/keypool-performance-ab/20261014T190140Z-3023756`.
- Two-repetition medians, four cores: standalone **7.342 Mkeys/s**, pipelined direct worker **7.336 Mkeys/s**, full SQLite Keypool **7.291 Mkeys/s**. Direct vs standalone **-0.1%**; SQLite vs direct **-0.6%**; SQLite vs standalone **-0.7%**, comfortably meeting the <5% throughput overhead acceptance target. Individual full Keypool runs **7.281** and **7.301 Mkeys/s**, each completing **512 × 2^20 = 536,870,912** committed keys in its own diagnostic campaign.
- The preceding high-load ~4.9 Mkeys/s session was environmental: an independent standalone run under low contention again measured ~7.317 Mkeys/s; the user suspects a concurrent FirLab build runner. This is consistent with contention, though the culprit was not independently established.
- End-of-run Pi thermal snapshots ~59–62°C, 2.4 GHz under load and `get_throttled=0x0`. No reported thermal/power throttling in measurements.
- **No production scan occurred during the benchmark.** Default Puzzle #71 campaign remains at **520 chunks = 545,259,520 committed keys**, `inflight=null`, `recovery_restarts=0`, `found=false`. Nothing auto-started.
- **Conclusion:** performance and bounded pipeline architecture are validated on actual Pi 5. Remaining production gates: real signal/kill/reboot recovery with disposable DB, disabled-by-default systemd start/stop/soak, heartbeat/health, hit notification, secure regtest-tested claim pathway and read-only mobile status. Do **not** conflate successful benchmark with unattended-production certification.

## 2026-10-14: continuous four-job pipeline redesign

- Prior Oct 13/14 physical Pi A/B/C results: standalone median 7.34M / 7.27M candidates/s, direct worker 7.10M / 7.01M, SQLite Keypool 6.31M / 6.46M. Pipeline, not a missing NEON optimization, accounted for the slowdown.
- New draft redesign: four producer-prefetched jobs, C++ four-slot FIFO, four independent slice claimers, separate ordered reporter, no per-job cryptographic thread barrier, one SQLite commit per completed job. A crash may replay a bounded window of at most four jobs; durable cursor and permutation remain unchanged. Existing Puzzle #71 database is compatible.
- ARM64 CI: worker protocol + known Puzzle #20 hit, fake-worker crash/restart, real-worker SQLite sessions, exhaustive post-HASH160 Puzzle #20 coverage and controlled precommit failure passed. Pi throughput impact measured separately above.
- Benchmark `tests/keypool-performance-ab.py` compares standalone vs **pipelined direct worker** vs **pipelined SQLite Keypool**, using separate diagnostic campaign DBs. Do not enable continuous service without physical Pi revalidation.

## 2026-10-13: exhaustive Puzzle #20 scheduler acceptance

- New isolated test: `python3 tests/keypool-puzzle20-exhaustive.py` (build `keyhunt-worker` first). **GitHub ARM64 CI worker-and-pool job passes.**
- Uses public solved Puzzle #20 with `[2^19,2^20)`, 64 permuted disjoint chunks of `2^13` keys, a fixed test seed placing known solution `0xd2c55` in the last dispatched chunk.
- Opt-in `KEYHUNT_WORKER_COVERAGE` emits **post-HASH160** `WORKER_SCANNED` records (1,024 keys/group), test verifies 512 unique groups = 524,288 keys. Worker slice dispatch and full permutation order are also verified, without altering the regular hot loop when trace is disabled.
- Deliberate interruption **after worker completion and before SQLite commit** forces exactly one chunk replay: 8 groups (8,192 attempted keys), zero other overlaps and no missing coverage. Final checkpoint 64/64; recovered known key independently verified and stored only in private temporary fixture.
- Fixture state/database is temporary and **cannot use the production default path**. The previously initialized Puzzle #71 SQLite campaign and its `next_i` remain untouched. Production command line still defaults to Puzzle #71.
- Next gates: run this test on the actual Pi 5, then compare 120-second sustained unique-completion throughput vs the proven ~7.34 Mkeys/s engine, and test SIGKILL/power-loss recovery on a disposable campaign.

## Validated winner and preserved control

**Current preferred *experimental* binary:**

```
keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1-neon
```

This combines native ARMv8 SHA2 SU0/SU1 dual-stream SHA256, four-lane NEON RIPEMD160, native 4×64-bit row field multiplication and symmetric 10-product squaring, incremental ECC center, exact Y parity of each compressed secp256k1 point, point-X subtraction simplification, exact one-target HASH160 lookup, and a SIMD in-register four-lane target-hit mask. **It still computes the complete SHA256 + RIPEMD160 cryptographic workload for every scalar.**

**Preserved control:** `keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1` (identical except full RIPEMD digest output/scalar matching). Earlier reference `...-field-mul-sqr` excludes point/direct improvements. Full names are in `Makefile` and `tests/arm64-neon-target-bench.sh`.

**Physical Pi 5 measurements (source: user's terminal output; logs reside only on their Pi):**

| Milestone | Four-core scanned scalar candidates/s | Notes |
|---|---:|---|
| True-parity + native SU2/NEON, 1024 group, original field | ~6.12M | Initial fast correct-parity baseline |
| Native 4×64 row MUL + native SQR | 6,719,160 | Faster; preserve old reference |
| Comba column MUL + SQR | 6,526,402 | **Rejected**: 2.9% slower than row |
| Algebraic point-X + single-target direct lookup | 7,214,924 | 2× short interleaved median |
| In-register NEON exact-target mask | **7,389,900** | 3× short interleaved median; +1.18% against full-digest control |
| 120-second sustained full-digest control | **7,216,582** | Single 120s control |
| 120-second sustained NEON target | **7,337,325** | +1.67% sustained against same-session control |
| Second independent 120-second NEON run | **7,336,683** | ~0.009% difference from first NEON |

For the sustained run: ~2.4GHz later-clock samples, hottest observed ~60.4°C, `vcgencmd get_throttled=0x0`. NEON early/late half rate −0.73% in the paired run, +0.18% in independent NEON run. This supports **sustained relative gain**, but there has been **only one long-duration control run**; don't overstate statistical certainty. Hashes/second from dual-prefix binaries must be halved to compare unique intended scalar candidates; true-parity binaries count one real scalar attempt per compressed key. Random chunk revisits are not deduplicated.

**120-second PMU A/B result, approximate absolute costs** for control vs NEON in-register: cycles/key 1272.3→1245.6 (−2.1%), instructions/key 1844.7→1761.3 (−4.5%), IPC 1.45→1.41, mispredicted branches/1000 candidates 2838→2785 (−1.86%) while branch-miss percentage 3.61%→4.05%. The **higher percentage is not higher absolute misses per candidate**. PMU counts run over full timeout, while Keyhunt's final 5-second status record covers only completed reporting intervals: script extrapolates full-window candidate count. These **absolute per-key values are estimates**. For electrical energy efficiency (joules/candidate), measure wall power separately; IPC alone is not an efficiency target.

## Reproduce the exact Pi run

```bash
cd ~/BITCOIN_ANALYSIS/bitcoin-puzzle/keyhunt
git status --short && git branch --show-current && git rev-parse HEAD
git pull --ff-only
# Build only the experimental candidate if needed:
make arm64-neon-target
# Correctness tests (run after any source changes; not every benchmark):
make arm64-neon-target-test
# Sustained 120s per variant, 4 cores, hardware PMU and thermal snapshots:
bash tests/arm64-neon-target-bench.sh
```

The benchmark accepts `KEYHUNT_BENCH_MODE=both|control|neon`, `KEYHUNT_BENCH_BINARIES` (space-separated exact built binary names; overrides mode), `KEYHUNT_BENCH_SECONDS=120`, `KEYHUNT_BENCH_THREADS="4"`, `KEYHUNT_BENCH_REPEATS=1`, `KEYHUNT_BENCH_CHUNK=0x100000`, `KEYHUNT_BENCH_PUZZLE=71`, `KEYHUNT_BENCH_PERF=0|1`, `KEYHUNT_TARGET` and `KEYHUNT_RUN_DIR`. It writes **timestamped** subfolders, raw logs, PMU, clock/thermal samples and TSV. Single-candidate-only run: `KEYHUNT_BENCH_MODE=neon bash tests/arm64-neon-target-bench.sh`. Set `KEYHUNT_BENCH_PERF=0` only if counters cannot be read. Benchmarking two variants sequentially means later runs may be hotter; for marginal (<2%) gains use reversed A/B order or >1 repetition.

**Correctness coverage previously passed:**
- `build/arm64/neon-target-check`: **20,480** exact four-lane SIMD masks vs completed RIPEMD160 digests, including 2–4 matching lanes and deliberate nonmatches;
- `tests/arm64-work-elimination-coverage.py`: same 18 solved keys in all variants, N=1 direct path activated, N>1 fallback;
- parity-even and parity-odd simulated #71, 140-bit and high 256-bit test vectors, Puzzle #20 recovered;
- 13,980 field operations/alias forms per kernel against independent Python big-integer oracle; additional SHA/NEON, ECC and solved puzzles in GitHub Actions.
**Passing fixtures is necessary but does not establish exhaustive keyspace coverage, long-term scheduling correctness or real-world hit spending readiness.**

## What failed, and why it matters

- **512 vs 1024 vs 2048 group size:** four-core true-parity throughput almost identical, 1024 remains sensible; no further group-size sweep without strong evidence.
- **Comba 4×4 column multiplication:** same 16 64-bit products, more carry dependencies/bookkeeping on this A76; slower (6.526M/s vs 6.719M/s row/square).
- **Optimising 'hot' symbols blindly:** dedicated SHA/RIPEMD/ECC improvements paid off, but eliminating Bloom/XXH64 for single target was much higher-value than rearranging multiplications.
- **Earlier throughput reporting bug:** non-1024 group size was hardcounted as 1024; fixed. Compare correct per-scalar throughput, not incorrectly doubled 512 and halved 2048 raw counters.
- **Original upstream GPU/Pollard BSGS headline figures:** operations and precomputed interval coverage are not equivalent to full compressed HASH160 candidates when #71 public key is unknown.
- **A previous test wiring bug:** initially direct-target optimisation landed in inactive endomorphism path, and a fixture wrote a literal backslash-n. Tests now require the exact N=1 fast path activation; avoid 'optimisations' not actually reached by the benchmark.

## Unanswered decisions for another agent

**Highest priority is search scheduling and actual coverage, not one more 1% math trick.** Verify bit-range endpoints, random chunk start semantics, exact scalar sequence for stride, tail clipping, restart and multi-thread overlap on instrumented small fixtures. The CLI parser and worker implementation do **not** provide durable disjoint-range checkpoints. Current random `-R` throughput is *attempts*, not audited unique #71 coverage. Add source-backed tests and any scheduler change only behind separate compile/runtime switches in this same PR.

Also audit upstream `address` vs `rmd160`, `xpoint`, `bsgs`/`-B`/`-k`, `-e`, `-I`, `-l`, `-r`/`-b`, `-R`, `-n`, `-S`, and `-z`; see companion document for applicability. Be suspicious of unverified assumptions about solved-key distribution or derivation patterns; a nonuniform search order doesn't improve uniform unknown-target odds unless a creator-bias hypothesis survives out-of-sample tests. No public key means no Kangaroo/BSGS advantage for #71.

Next purely computational experiments *already identified*, but not yet validated: hoist repeated `temp_stride.SetInt32(4); temp_stride.Mult(&stride)` out of every four-key block; precompute constant negative generator Y; bypass the four scalar lane checks on all-zero NEON target mask; then measure instruction-level branch misses and impact. Document test harness, output data and reversibility before promoting anything.

## Safety and operation

- Work only against the public, deliberately funded Bitcoin puzzle target and synthetic/solved fixtures. No production private keys or wallet secrets in GitHub/issues/logs.
- This project is a lottery search, not a plausible profitable CPU search at ~7.34M candidates/s across 2^70 possible keys. Don't substitute 'total attempted' for probability of success.
- Physical Pi outputs under `~/BITCOIN_ANALYSIS/bitcoin-puzzle/runs/` are **not** in GitHub. Agent cannot claim to have inspected a raw perf trace or range ledger unless user shares it.
- GitHub writes belong on `perf/pi5-arm64` (same PR #1); no `main` merge. Run GitHub Actions after any code changes; use the Pi only when a physical performance check is necessary.
- Keep docs updated with tested commit, timestamp, feature flags, data, and explicit 'measured' vs 'hypothesized' distinction.
