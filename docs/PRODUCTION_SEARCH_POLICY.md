# Production search policy: Puzzle #71 on Pi 5

**Status:** design contract, **not implemented**. Updated 2026-10-11.  
**Branch:** `perf/pi5-arm64`, draft [PR #1](https://github.com/samuelcstl/keyhunt/pull/1).  
**Agent entrypoint:** [AGENTS.md](../AGENTS.md).  
**Evidence and mode review:** [upstream modes/search space](../research/2026-10-11-keyhunt-modes-and-search-space.md), [agent handoff](AGENT_HANDOFF_PUZZLE71_PI5.md).

This document is the bridge between the proven experimental Pi5 engine and an unattended, restartable lottery scanner. Do not mistake this policy for an existing daemon, a tested scheduler or an achieved search-coverage guarantee. Do not enable services or alter `main` without explicit user approval.

## 1. Evidence and immutable search contract

The current target is the publicly established **Bitcoin Puzzle #71** compressed P2PKH address:

```text
address = 1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU
HASH160 = f6f5431d25bbf7b12e8add9af5e3475c44a0a5b8
L       = 0x400000000000000000          # inclusive 2^70
U       = 0x800000000000000000          # exclusive 2^71
S       = U-L = 2^70                   # 1,180,591,620,717,411,303,424 keys
compressed public key only; true secp256k1 Y parity
stride  = 1
```

The public key is not known in the sources checked as of 2026-10-11:
[Needlespace #71](https://needlespace.com/en/puzzle/71),
[range calculator](https://lotterypzl.org/tools/range/).
Recheck live chain status *before* a production run; if the pubkey becomes public or puzzle is solved, reconsider search method and economics.

The user's current **experimental** command is:

```bash
-m address -b 71 -l compress -R -n 0x100000 -t 4 -q -s 5
```

with the single-target file in `~/BITCOIN_ANALYSIS/bitcoin-puzzle/runs/bench71/target.txt`. The current leading **experimental** binary is
`keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1-neon`.
The handoff contains exact validated rates, verification coverage and known limitations. A proven 120-second Pi5 run was ~7.337 million **attempted** scalar candidates/second; not globally distinct coverage or an energy measurement.

## 2. Upstream modes: explicit production choice

| Mode / switch | Decision | Why |
|---|---|---|
| `-m address`, `-l compress` | **Use** | Tested exact P2PKH HASH160 of one compressed key per scalar |
| `-m rmd160` | Valid alternative, not a shortcut | Same expensive HASH160 hash steps, only target file format changes; needs mode-specific tests |
| `-m xpoint` | **Not applicable** | Requires known public-key X; the target supplies only HASH160 |
| `-m bsgs`, `-B`, `-k` | **Not applicable** | Point-known discrete logarithm, not HASH160 preimage inversion |
| Pollard Kangaroo | **Not applicable** | Also needs target public point |
| `-e` | **Do not use** | Endomorphism moves most derived scalars outside the restricted 71-bit interval and disables our true-parity fast path |
| `-I 1` | Required effective stride | Nonunit stride skips/scatters scalars and can cross bounds; zero stride may produce repeated attempts |
| `-b 71` or `-r L:U` | Use **one**, not both | `-b` overrides accepted explicit ranges in current source; `-r` invalidity can fall back silently to full interval |
| `-R` | Research-only random chunks, until coverage-audited | Uniform-looking chunk starts are not unique, range-clipped or restartable |
| `-n 0x100000` | Current control | 2^20 scalar-attempt chunk, separate from 1024-point ECC group; must be a multiple of compiled ECC group |
| `-S` | **Not a work checkpoint** | Precomputation/Bloom-data cache, not processed-scalar ledger |
| `-z`, `-6`, `-M`, `-d` | No production speed claim | Bloom multiplier, skip checksum, screen matrix, debug; no demonstrated advantage to N=1 target |
| `vanity`, `minikeys`, retired `pub2rmd` | Not applicable | Different objective, key format, or removed code path |

For all options, use *current source and tests*, not merely old upstream README examples.

## 3. Search-space choice: priority is coverage integrity

For uniformly unknown `k ∈ [L,U)`, no contiguous subrange or patterned subsequence has a privileged probability. A purported creator bias must be quantified on independent, held-out solved examples, accounting for how those puzzles were selected and solved, before weighting the search. Observing that all known keys have the required bit length supplies **no additional predictive information** within the interval.

At `r ≈ 7,337,000` attempts/s:

| Lifetime | Approx attempted keys | Best-case chance with distinct uniform attempts |
|---|---:|---:|
| 120 seconds | ~880,440,000 | 7.46×10^-13 |
| One day | ~634 billion | 5.37×10^-10 |
| One year (365.25 days) | ~231.5 trillion | ~1.96×10^-7 (~0.0000196%) |
| Ten years | ~2.315 quadrillion | ~1.96×10^-6 (~0.000196%) |

These are small *search* probabilities, not expected profit, insurance against reward sniping, or evidence that a key is present. Exact calculations assume the challenge’s key was uniformly selected within the announced interval. Keyhunt's printed candidate total is **attempts**, not unique covered keys.

### Three credible scheduling policies

**A. Existing random-start lottery (current, simplest):** sample `base ∈ [L,U)`, scan a contiguous block of `C=0x100000` scalar candidates, repeat. Overlap is negligible at current coverage fraction, but the final part can run outside `U`; restarts cannot prove any useful cumulative coverage and a random base is not aligned to the chunk grid.

**B. Deterministic contiguous sweep:** allocate exact grid chunks `[L+iC,L+(i+1)C)` in increasing order. Easy to audit and resume; uniform unknown key gives the same hit chance per **distinct** candidate. Scanning from the bottom is not inherently advantaged.

**C. Deterministic, scrambled, nonrepeating chunk order: recommended long-term option.** Keep a monotonic allocation counter `i=0,1,…`, map through a **provably bijective permutation** `π` of chunk indices, scan `[L+π(i)C,L+(π(i)+1)C)`. Produces the lottery-like scatter of random search while guaranteeing disjoint chunk *assignments*. Do not claim the permutation is random or cryptographically secure merely because it looks scattered. Use documented reproducible seed and a tested bijection. This is not coded yet.

The #71 interval is exactly divisible by the current chunk size:

```text
S = 2^70
C = 2^20 = 1,048,576 keys/chunk
M = S/C = 2^50 = 1,125,899,906,842,624 possible chunk indices
start(i) = L + π(i)*C
end(i)   = start(i)+C       # exclusive; last chunk ends exactly at U
```

A simple example of a **bijection**, not an endorsed cryptographic randomizer, is `π(i)=(a*i+b) mod 2^50` with odd `a`. Its invertibility ensures no repeated chunk IDs, but its linear pattern may be undesirable if the user intends an unpredictably scattered order. A tested 50-bit permutation/Feistel design could avoid obvious ordering correlations. Neither approach reduces the search entropy.

### State and restart semantics

- Persist **next allocation counter**, permutation parameters/version and worker in-flight chunk IDs. Record *completed* status **only after** the worker has finished all in-range scalars and result verification.
- On restart, **replay** assigned-but-unacknowledged chunks rather than silently skipping them. Crash-safe recovery may repeat a bounded amount of work. "Exactly once execution" is not a realistic durability guarantee across hard crashes; **no missed chunks and bounded replay** is the actual objective.
- Four workers should claim disjoint IDs atomically. If chunks can complete out of order, persist a contiguous-completion watermark plus a small bounded set of completed jobs above it. Persist atomically (SQLite transaction/WAL or rigorously tested journal), with record checksums/versioning and process-exclusive lock.
- Avoid an indefinite **one-row-per-chunk** ledger: ~7 chunks/s becomes >2 billion rows over ten years. O(threads/in-flight) or compact acknowledged-range state is more suitable than an append-only permanent row per small chunk.
- Counters distinguish attempts, **in-range** attempts, unique **completed** chunks, replays, abandoned work, and out-of-range tail attempts. Never equate attempted scalars/s to effective unique coverage/s.
- Associate checkpoints with `{target HASH160, [L,U), compression mode, stride, chunk size, permutation seed/algorithm/version, binary build hash}`. Resume must reject incompatible configuration and never silently expand the interval.
- Positive target hits must be verified by an independent full compressed SEC1→SHA256→RIPEMD160 path before triggering any user-visible notification. Never log recovered private scalars to GitHub or publish wallet material.

## 4. Audit risks found in *current* code (no code fix yet)

1. **Ranged random start vs chunk bounds:** `thread_process` calls `key_mpz.Rand(&n_range_start,&n_range_end)` and scans a whole `N_SEQUENTIAL_MAX` chunk. It does not generally clip to `U` and does not choose only aligned chunk IDs.
2. **Sequential end race:** end check (`n_range_start.IsLower(&n_range_end)`) is outside the assignment mutex. Two or more workers may pass the condition then allocate a final full chunk even if another worker already advanced beyond `U`. This must be proven by deterministic small-range tests, not just inferred.
3. **Stride zero / bounds:** `-I` is parsed into `Int stride` without a visible positive nonzero validation before generator initialization. Do not allow zero/nonunit stride into strict-coverage mode.
4. **Partial RNG reads:** on Linux `rndl()` in `secp256k1/Random.cpp` accepts `getrandom(&r,sizeof(unsigned long),GRND_NONBLOCK)` if **bytes_read > 0**, not only if it returned the full requested length. A positive *short* read could return partially uninitialized data. That is a specific robustness defect to test/fix before relying on random sampling; normal entropy-ready full reads do not establish that the short-read branch is safe.
5. **RNG fallback:** failed/nonpositive getrandom reads fall back to a process-global Mersenne Twister. For a lottery scanner, an explicit seeded, auditable policy with exact error handling is better than silently substituting a weaker generator.
6. **Surprising CLI fallback:** invalid `-r` bounds may trigger a full-keyspace fallback; `-b` silently overrides valid `-r`. Production validation must fail closed on unexpected target, range or mode.
7. **Statistics and clock:** `steps[]` and the last 5-second status snapshot show scanning speed, not durable coverage. Physical benchmarks showed PMU wall duration differs from last Keyhunt completed reporting interval; approximate per-candidate PMU estimates require aligned windows.

None of the above proves that previous known-key search outputs were wrong. They show why a fast, correct cryptographic inner loop is not yet an audited long-running scheduler.

## 5. Required verification before unattended execution

Implement an **instrumented small-range scalar-coverage test mode**, not just known-hit fixtures. It must emit exact candidate scalar IDs for controlled tiny test intervals and compare them against the mathematical expected set. At minimum:

1. Nonchunk-aligned interval length, exact chunk-sized interval, upper limit near the curve order, and a range whose left endpoint is not chunk-aligned.
2. `-n` at compiled ECC-group minimum and multiples; one/two/four workers; real stride 1, plus clearly validated rejection or semantics for `-I 0` and `-I >1`.
3. Confirm no lower- or upper-bound scan leakage when strict mode enabled. Confirm every in-range scalar exactly once in a complete deterministic single-machine run.
4. Concurrent assignment stress near the final chunk: zero gaps and no duplicate **completed** chunk assignment (crash recovery replay excepted).
5. Interrupt and hard-kill/restart at every state transition: assigned, partially scanned, completed but uncommitted, committed. Verify all chunks either complete or safely replay, no silent loss.
6. Repeat with permutation identity and scrambled bijective order; permutation must visit all chunk IDs without duplicates in small domains, then satisfy mathematical bijection invariants for the real `2^50` domain.
7. Test `getrandom` short/failed reads and startup/seed errors with injected RNG results; reject uninitialized buffers.
8. Verify positive-hit path with synthetic challenge key and independently recompute SHA256+RIPEMD160; ensure no secrets appear in regular progress logs.
9. Verify source-controlled test target/mode fingerprints and daemon restart options, including graceful stop and SIGKILL.
10. Ensure benchmarks remain on the Pi at 120 seconds/four cores, monitor sustained temp/frequency/throttling, CPU scheduling and other system services. Low-priority process execution must not starve Pi orchestration.

No scheduler implementation, daemon activation, hardware change, private-pool spending transaction or targeted probabilistic key bias is authorized by this document alone.

## 6. An executable production roadmap for the next agent

**Phase 0: prove coverage semantics.** Add source-controlled small-range tests exposing attempted private scalars and exact boundaries in diagnostic mode; confirm the current random and sequential bugs before introducing a new scheduler.

**Phase 1: minimal bounded-chunk allocator.** Add a strictly validated `[L,U)` scheduler with `C` divisible by ECC group size, correct tail clipping, and deterministic identity permutation. Keep original `-R` available for research, but don't label it resumable.

**Phase 2: scrambled coverage + checkpoints.** Add tested permutation, versioned atomic work journal, per-worker in-flight state, bounded replay and restart/failure injection tests. Prefer a compact watermark/in-flight structure to one database row per chunk forever.

**Phase 3: unattended service.** Non-root runner under `systemd` or equivalent, low scheduling priority, explicit start/stop, graceful drain, basic health/thermal counters, bounded local log retention, no personal secrets in logs, and user-approved notification on independently verified hits. Do not start automatically until authorized.

**Phase 4: end-to-end proof.** Compare full candidate correctness and completed unique chunks against the old baseline; 120-second/4-core sustained throughput and measured wall energy if available; 24h stability only when the user opts in. Keep the proven ARM64 NEON control available for rollback.

**Decision gate:** with no credible creator bias and no public key, choose **C** (scrambled disjoint chunk assignments) for the long-running Pi daemon **after** proof of coverage and crash recovery. Until then the existing random-start engine is an experimental lottery scanner, not a production coverage engine.
