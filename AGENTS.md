# Agent entrypoint: Keyhunt Pi5 Bitcoin Puzzle #71

This repository is an experimental fork of AlbertoBSD/keyhunt, actively worked on in **PR #1**, branch **`perf/pi5-arm64`**. Do **not** merge to `main` without the user's explicit approval.

## Required context, in order

1. [Complete agent handoff](docs/AGENT_HANDOFF_PUZZLE71_PI5.md). This is the authoritative record of hardware, tested versions, benchmarks, verification and open questions.
2. [Upstream modes and Puzzle #71 search-space audit](research/2026-10-11-keyhunt-modes-and-search-space.md). Read *before* recommending `-e`, `-I`, `-m bsgs`, `-R`, `-n`, or changing the private-key range.
3. [Production search KISS v1 specification](docs/PRODUCTION_SEARCH_POLICY.md). Authoritative scope: one local controller, one persistent four-core worker, seeded non-repeating chunks, one SQLite progress counter; no distributed pool in v1.
4. [Pi5 code-level waste audit](research/2026-10-11-pi5-architectural-audit.md).
5. [GPU source-level comparison](research/2026-10-11-gpu-source-audit.md).

## Known-good computation and limits

- Working target: Puzzle #71 compressed Bitcoin P2PKH, target address `1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU`; public key is not known in the reviewed sources.
- Valid private-key interval: `[0x400000000000000000, 0x800000000000000000)`, exactly `2^70` candidates.
- Pi5 four-core native ARM64 preferred experimental binary:
  `keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1-neon`.
- Full-digest baseline for same code path:
  `keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1`.
- Physical Pi5 sustained 120s NEON throughput observed twice:
  7,337,325 and 7,336,683 **attempted** scalar candidates/s. A single 120s control observed 7,216,582/s; no thermal throttling.
- `-R` samples random **chunk starts**, not durable, globally unique key coverage.
- BSGS, Pollard's Kangaroo and `-m xpoint` require the target's public key (or its X coordinate). Do not compare public-key-known equivalent 'Tkeys' figures with the unknown-public-key HASH160 workload.

## Reproducible Pi commands

```bash
cd ~/BITCOIN_ANALYSIS/bitcoin-puzzle/keyhunt
git status --short; git branch --show-current; git rev-parse HEAD
make arm64-neon-target-test                 # after code changes
bash tests/arm64-neon-target-bench.sh      # 120 s each for control vs candidate
```

Use `KEYHUNT_BENCH_MODE=neon` for a targeted test of only the NEON candidate; `KEYHUNT_BENCH_BINARIES` allows arbitrary built binaries without rerunning historical variants. User's target file: `~/BITCOIN_ANALYSIS/bitcoin-puzzle/runs/bench71/target.txt`. Raw run outputs are **on the Pi**, not committed to GitHub.

## Non-negotiable engineering rules

- Correctness before benchmark claims: oracle field checks, even/odd compressed parity, synthetic 71/140/256-bit solved fixtures, 18 known keys, real single-target fast-path activation and multiple-target fallback where applicable.
- Benchmark *full end-to-end* real scalar candidates/s, typically four-core **120-second** Pi trials, with CPU clocks, thermals, `perf` cycles/instructions and mispredicted branches **per candidate**. Measure marginal improvements in reversed order/repeated runs.
- Don't claim that higher IPC, fewer source lines, or a larger 'keys/s' counter proves a faster or more power-efficient search. A PMU per-key metric based on extrapolated snapshots is an **estimate**, not exact.
- Keep proven control available; experimental changes isolated and reversible. CI correctness does **not** replace physical Pi5 performance testing.
- No keyspace scheduler overhaul until exact-range/stride/thread-boundary and restart coverage tests exist. No unfounded creator-derived bias or assumption that transformed ECC scalars are within the 71-bit interval.
- Avoid putting private user data, private keys or wallet credentials into source, logs, PR comments or tests. Work on the public intentional puzzle and synthetic/solved fixtures.
- Update the handoff and audit if source semantics, default flags, benchmark method, or measured state changes.
