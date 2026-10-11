# Upstream modes, CLI switches and Puzzle #71 search-space audit

**Audited:** 2026-10-11, against [this fork's `keyhunt.cpp`](../keyhunt.cpp), [`secp256k1/Int.cpp`](../secp256k1/Int.cpp), [`Random.cpp`](../secp256k1/Random.cpp), [upstream README](https://github.com/AlbertoBSD/keyhunt/blob/main/README.md) and [BSGSD.md](../BSGSD.md).  
**Branch:** `perf/pi5-arm64`; **status: research/documentation only**, no new scheduling code, no claim of verified exhaustive coverage.  
**Companion:** [agent handoff](../docs/AGENT_HANDOFF_PUZZLE71_PI5.md).
**Production handoff:** [disjoint scheduling, exact range and restart contract](../docs/PRODUCTION_SEARCH_POLICY.md), **not yet implemented**.

## Executive decision

For Bitcoin Puzzle #71, where the **public key is not known**, the appropriate presently verified production-computation path is a **compressed P2PKH address/HASH160 scan over the 2^70 candidate private keys**, using the exact-parity Pi5 ARM64 + NEON target-match binary. Existing upstream BSGS and xpoint advantages **require a known public key** and cannot be applied to an address-only hash160 target. No general GPU/endomorphism/key-stride transformation reduces the intended interval entropy.

The next high-value problem is **coverage-quality engineering**, not another microbenchmark: verify random/sequential chunk bounds, checkpointing, duplicate overlap and multi-thread allocation on small fixtures; then decide between ephemeral lottery sampling and deterministic resumable scheduling. There is **no evidence-based reason to prefer a special low-bit, high-bit or patterned subregion** of #71 merely because previously solved keys look interesting.

## 1. Actual puzzle definition and search-space choice

External public status checked on 2026-10-11:
- [Needlespace puzzle 71](https://needlespace.com/en/puzzle/71) lists it unsolved, with public key unknown, P2PKH address `1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU`.
- [Bitcoin Puzzle 71 public range](https://www.btc-puzzle.com/introduction): `0x400000000000000000` through `0x7fffffffffffffffff`, inclusive.

Canonical half-open set:

```text
L = 0x400000000000000000 = 2^70
U = 0x800000000000000000 = 2^71         # EXCLUSIVE upper bound
S = U - L = 2^70 = 1,180,591,620,717,411,303,424 scalars
```

**Exact current search flags:**
```bash
-m address -f "$HOME/BITCOIN_ANALYSIS/bitcoin-puzzle/runs/bench71/target.txt" \
-b 71 -l compress -R -n 0x100000 -t 4 -q -s 5
```

`-b 71` sets the high bit (start = 2^70, end = 2^71); this is not a full 2^71-key interval. `-l compress` is essential. Address-based search with `-m rmd160` can check the same underlying 20-byte HASH160 when the correctly encoded hash file is supplied; it does **not** avoid computing SHA256+RIPEMD160 for each candidate. Keep current address-mode control unless another mode is fully validated.

At the observed 120-second NEON rate ~7.337 million *attempted* candidates/sec:
- 120 seconds: ~880 million candidates, ~7.46×10⁻¹³ of the interval.
- 24 hours: ~633.9 billion, ~5.37×10⁻¹⁰ of the interval.
- 365.25 days: ~231.5 trillion, ~1.96×10⁻⁷ of the interval, or ~0.0000196% uniform-hit probability if all trials effectively distinct.
- 10 years: ~0.000196% uniform-hit probability.
- Full straight-line sweep at this rate would take ~5.10 **million years**; expected placement of a uniformly chosen key in a deterministic sweep ~2.55 million years.
These are mathematical expectations, **not** forecasts of reward availability, market value or competition. Random sampling with replacement yields `1-(1-1/S)^n≈1-exp(-n/S)`, and an ideal unique scan yields `n/S` for n≤S. For current sample counts the difference is negligible relative to S; deliberate range restrictions can cost enormous probability without credible nonuniform priors.

## 2. Verified CLI mode and option matrix

### Search modes

| Mode / switch | Upstream function | Applicability to #71 | Source-backed caveat |
|---|---|---|---|
| `-m address` | Compare P2PKH address HASH160 | **YES; established winner** | Compressed-only exact Y; Pi5 optimized single-target path tested |
| `-m rmd160` | Compare raw 20-byte HASH160 target file | **YES, mathematically equivalent target check** | Different input encoding; run mode-specific hit fixtures before changing; no SHA/RIPEMD bypass |
| `-m xpoint` | Compare public-key X coordinates | **NO, missing target public key/X** | Faster per candidate because it omits HASH160; not comparable |
| `-m bsgs` | Baby-step/giant-step on **known pubkey** | **NO for address-only #71** | Enormous printed Tkeys/s are *interval-coverage equivalents*, not independent HASH160 evaluations; memory and precomputation tradeoffs. Reconsider only if target pubkey revealed |
| `-m vanity` | Match chosen address prefixes | **NO** | A full specified P2PKH address is not efficiently converted into a vanity prefix goal |
| `-m minikeys` | Search Casascius-style minikey formats | **NO known link to creator's key derivation** | Different candidate generation; not a proven restriction on puzzle entropy |
| `-m pub2rmd` | Older experimental public key to RIPEMD probe | **RETIRED** | Current CLI explicitly prints "Mode pub2rmd was removed" and exits, despite README preserving historical prose |
| `-c eth` | Ethereum / KECCAK address processing | **NO** | Bitcoin P2PKH target uses HASH160 |

### Search bounds, stride and scheduling

| Switch | Actual behavior from current source | Advice |
|---|---|---|
| `-b 71` | Builds start=2^70, end=2^71; later `FLAGBITRANGE` assignment overrides valid `-r` bounds | Prefer **one** bound expression, not `-b` plus `-r` |
| `-r HEXSTART:HEXEND` | Parses hex, zero start incremented to 1; equal/out-of-order/invalid ranges have surprising handling, including swapping or silently falling back to full range | Test exact printed start/end and scan coverage before use. End acts like **exclusive** boundary for random-start selection; worker does **not** generally clip chunk at end |
| `-R` | Sets `FLAGRANDOM=1`; each worker repeatedly chooses a random base `key_mpz.Rand(&start,&end)`, then scans `-n` sequential keys before next random base | **Random chunks, not a persistent disjoint-range scheduler.** No cross-run checkpoint |
| Without `-R` | Sequential start assignment, global `n_range_start += N_SEQUENTIAL_MAX` under mutex, until start crosses end | Prefer for a finite reproducible experiment, but check thread-side end guard, tail overscan and concurrency; end condition checked outside lock |
| `-n 0x100000` | A **chunk of 1,048,576 attempted scalars**; CPU ECC group size (1024) is separate | Validated throughput reference. Must be ≥ compiled `CPU_GRP_SIZE` and divisible by it for address/rmd160/xpoint; non-BSGS default is much larger (2^32). Benchmark alternative chunk sizes only if startup/chunk overhead matters |
| `-I STRIDE` | Integer step between successive candidate scalars; changes `init_generator` to compute `stride*G` and hot-loop key increments | `stride=1` scans every scalar in chunk. `stride>1` skips keys and can walk outside the selected bit window; does **not** increase uniformly valid #71 coverage per candidate. Does not apply to BSGS |
| `-t N` | Worker threads | Four Pi5 cores currently tested; no proof that >4 helps |
| `-s SECONDS` | Throughput/status frequency | Five-second snapshots are **not** a unique coverage ledger; PMU timing windows need alignment |

### Other options that can be overlooked

| Switch | Purpose | Priority for #71 |
|---|---|---|
| `-l compress` | Only compressed public-key HASH160 | **Critical**. Solved puzzle outputs tested match compressed format. Uncompressed/both waste effort for #71 |
| `-e` | Curve endomorphism maps and negative-point variants | **Avoid** for fixed 71-bit interval: almost all transformed scalars lie outside that interval. Current `parity_search` fast path is deliberately disabled with `FLAGENDOMORPHISM`. Don't mistake 3×/6× derived hashes for 3×/6× in-range scalars |
| `-B` | BSGS-specific sequential/backward/both/random/dance | **Irrelevant** to address brute force; `-R` also selects BSGS random mode |
| `-k` | BSGS baby-step table factor, trading RAM for giant-step work | **Irrelevant** without pubkey |
| `-S` | Save/read precomputed Bloom data and BSGS tables | Startup caching, **not a keyspace search checkpoint**. For one-target NEON equality, lookup Bloom is already bypassed |
| `-z` | Bloom size multiplier | No search-loop gain for exact N=1 comparison; may add memory/startup cost |
| `-6` | Skip checksum on cached BSGS/data files | Avoid: weakens integrity, no documented benefit to one-target loop |
| `-q`, `-M`, `-d` | Quiet threads, screen matrix, debug | Quiet for benchmarks; avoid matrix/debug overhead |
| `-v` | Vanity target patterns | Not a full address equality improvement |
| `-C`, `-8` | Minikey prefix/custom Base58 alphabet | Not relevant to puzzle compressed private scalar interval |

**Important documentation inconsistency:** upstream `menu()` says `-R` is "default behavior", but this fork initializes `FLAGRANDOM = 0`; the default non-BSGS mode is sequential until `-R` is explicitly supplied. The README has retired-mode examples. Verify code, not prose.

## 3. What the current random scheduler really does

Relevant code:
- CLI parser: `keyhunt.cpp` ~494–785.
- Range preparation: ~820–866.
- `-n` chunk validation: ~869–895.
- Worker: `thread_process` ~2587–2612: random `Rand(min,max)` **or** synchronized sequential `n_range_start += N_SEQUENTIAL_MAX`; then `count<N_SEQUENTIAL_MAX` point/hash sweep.
- RNG: `Int::Rand(min,max)` in `secp256k1/Int.cpp` ~751–763; draws 256 random bits using `rndl()`, reduces modulo `max-min`, adds `min`. On Linux `rndl()` in `secp256k1/Random.cpp` uses `getrandom` with Mersenne-Twister fallback.

### Randomness is not the obvious weakness here

For exact `-b 71`, `max-min = 2^70`, which **divides 2^256**. Therefore the `256-bit random integer % 2^70` operation is **exactly unbiased** if its input bits are uniform; no modular-reduction bias exists for this particular interval. However this does not prove RNG correctness/independence, unique coverage, or valid post-chunk clipping. For arbitrary ranges not a power of two, ordinary modulo reduction can introduce a small bias. The local PRNG fallback deserves separate robustness tests before unattended long-running deployment.

### Actual coverage issues to test, not assume fixed

1. **Random chunk may cross the upper bound.** Base is sampled from `[L,U)` irrespective of `-n`; the worker then processes a full chunk without an explicit `min(U-base,n)` cap. That can spend tiny fraction of work outside Puzzle #71. For ideal uniformly sampled starts, edge overhead is roughly `chunk/(2S)`, negligible with 2^20 against 2^70, but **not acceptable for claiming strict audited coverage**.
2. **Sequential tail may also cross upper bound.** Dispatcher tests only whether *start* is below upper end and assigns full `-n`. A lock covers updating global start, but the end check is outside that lock, which should be tested for concurrent dispatch races.
3. **No durable work ledger.** Restart loses the previously attempted random chunks; a sequential run also has no built-in persistent checkpoint of completed vs assigned segments. `-S` does not fix this.
4. **Random chunks overlap.** Overlaps can occur even when exact starts differ, because starts are not chunk-aligned. The theoretical wasted fraction stays tiny at Pi5/71 scale, but the counter never subtracts duplicates; at large multi-machine scale a disjoint assignment ledger is better.
5. **Stride and range interact.** Arbitrary `-I` affects scalar values covered and may overshoot the upper bound much sooner. Testing `-I` with small fixtures is essential before using nonunit stride in production.
6. **Random restart vs sequential resumption.** Random mode has no remembered candidates by design. For deterministic coverage, explicit audited segment allocations/acknowledgement must persist on disk; writing down one console "Base key" is not a reliable resume point.

**Key conclusion:** equal-sized random and disjoint deterministic samples have essentially equal immediate chance against a uniformly distributed unknown key *for the same distinct candidate count*. Deterministic sampling becomes preferable for proof of no repeat, safe restarts, range coordination and future scaling. Search-order heuristics only beat it under a quantitatively supported nonuniform prior.

## 4. Search-space tactics that do NOT confer an automatic advantage

- **Change target #71 to #72, #73 etc.?** The intervals are disjoint, and each next difficulty has twice as many keys. Without an independent prior/reward model, #71 remains the least expensive unsolved *address-only* puzzle, as publicly listed at this review.
- **Combine multiple puzzles in one hash pass?** A single scalar falls within only one nonoverlapping canonical puzzle interval. Multi-target HASH160 matching is reusable only if targets plausibly share the scanned scalar window, not when targets live in disjoint puzzle windows.
- **Use `-m bsgs`/Pollard kangaroo faster than SHA256?** Only against public-key-known discrete-log targets. HASH160 of an unpublished public key cannot be substituted for an EC point in those algorithms.
- **Endomorphism to sextuple #71 chances?** Maps to other scalars modulo curve order, overwhelmingly outside the 71-bit window. A nominal "6 checks" rate is not 6 correct in-range candidates.
- **Only check a privileged hex prefix/low Hamming weight?** Changes where you look, not how likely it is to contain a uniformly unknown answer. Creator-key derivation speculation might support a prior only if derived/tested from held-out solved instances without leakage and with a documented statistical advantage; otherwise prefer uniform/disjoint coverage.
- **Change `-n` to a huge value?** Could reduce scalar base-point recomputations, but may worsen stop/checkpoint granularity and should be performance-measured on 120-second Pi trials. Not a larger entropy reduction.
- **Use `-m rmd160` instead of `-m address` for speed?** Both operate on the same hashed 20-byte target after file parsing and currently share the hot worker. If raw HASH160 input is already known, it may trim startup decoding, not compute a different puzzle.

## 5. Recommended next validation matrix (not yet executed)

**Priority 0: coverage correctness before a scheduling rewrite.** Run source-controlled small-range fixtures against known scalar/address targets, tracing exact start and end of each assigned chunk; use 1, 2 and 4 workers, random and sequential, `-n` 1024/4096/2^20, ranges exactly matching and not matching chunk boundaries, stride 1 and other explicit strides. Assert zero skipped scalars in a deterministic exhaustive test, zero out-of-range scalars when `strict` is promised, and identical found keys in random/controlled seeded cases. Existing known-key fixtures do **not** prove exact no-duplicate/no-gap coverage.

**Priority 1: separate `scheduler/coverage` telemetry** from hash throughput. Count actual in-bounds scalar attempts and globally **distinct** covered intervals (with an allocation ledger), invalid-tail attempts, repeated chunks, and completed-vs-assigned chunks after interruption. A disk ledger must be atomic/crash-consistent before advertising resumability.

**Priority 2: choose policy.** For the present single-device lottery, `-b 71 -R -n 0x100000 -I 1 -l compress` is reasonable; random overlap is astronomically minor and all 120-second throughput numbers correspond to this workload. For prolonged or multi-device running, prefer a deterministic/range-partitioned policy with checkpointing once tested. Do **not** silently change the runner from random to sequential because that alters the user's strategy.

**Priority 3: benchmark `-n` independently**, with the validated NEON winner and unchanged scalar step/range, if required. A targeted, sustained comparison of 2^18, 2^20 and 2^22 keys per chunk suffices to understand restart overhead. Don't rebuild/re-run obsolete variants.

**Priority 4: only if a new public key becomes known**, revisit xpoint, BSGS, Pollard's Kangaroo on the relevant target and estimate actual RAM/compute trade-offs. Do not use BSGS headline throughput for current #71.

## 6. Source integrity and further checks

This audit documents source behavior, not all dynamic paths. The CLI has historical oddities, flags with mode-dependent behavior, and potentially surprising `-r` fallback. Avoid asserting strong properties such as "uniform random", "exact range clip", "deterministic exhaustive", "no duplicate work", "all saved" or "restartable" without exercising the actual Pi binary on synthetic fixtures. Guard any performance optimisation behind feature flags, preserve the known-good NEON binary, and record exact git commit/build/benchmark log if an agent implements coverage changes.

No production search-space partition, custom heuristic, or background monitoring was started by this document.
