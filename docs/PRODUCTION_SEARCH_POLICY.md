# Keyhunt production search: KISS v1

**Status:** experimental KISS v1 implementation in this PR; ARM64 CI passes for worker, SQLite crash recovery and real-worker/controller integration. Physical Pi sustained benchmarking and power-loss recovery remain validation gates. Updated 2026-10-13.  
**Scope:** local Raspberry Pi 5, Bitcoin Puzzle #71; work in [PR #1](https://github.com/samuelcstl/keyhunt/pull/1) only. No merge to `main` or automatic service activation without approval.

## Goal

Run our proven ARM64 Keyhunt engine unattended, with reproducible, non-overlapping search assignments and safe restart. Keep the fast cryptographic loop intact. A crash may replay the last unfinished chunk; it must never silently skip one.

## Fixed campaign

- Target: compressed P2PKH `1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU` (`HASH160=f6f5431d25bbf7b12e8add9af5e3475c44a0a5b8`).
- Exact scalar interval: `[L,U)=[0x400000000000000000,0x800000000000000000)` (`2^70` keys); stride `1`, true compressed-key Y parity.
- Work chunk: `C=2^20` keys; `M=2^50` disjoint chunks. These divide the #71 range exactly.
- One seed sampled securely **once per campaign** and stored. A versioned, **bijective** 50-bit permutation `pi(seed,i)` scrambles chunk order without replacement:
  `start=L+pi(seed,i)*C`, `end=start+C` (exclusive), for `0 <= i < M`.
- Use a small tested Feistel permutation (inspired by [Intel Arc Puzzle 71's `tools/hunt.py`](https://github.com/orfeomorello/Intel-Arc-Puzzle-71/blob/main/tools/hunt.py)), **not** fresh random starts or upstream `-R`. This scatters work; it does not improve the probability of a uniform unknown key per distinct attempt.

A campaign's target, bounds, stride, chunk size, seed, permutation algorithm/version, and worker interface version are immutable on resume. Refuse incompatible settings rather than silently starting a different search.

## Two local processes, one simple protocol

1. **`keypoold`**: one controller, started manually via `systemd`; owns the schedule, durable progress, worker lifetime and status.
2. **`keyhunt-worker`**: one long-lived child using up to four Pi cores; reuses the existing optimized ARM64/NEON search loop, accepting exact bounded jobs.

Use newline-delimited JSON over the child's **stdin/stdout** for v1. A job carries `{id,start,end_exclusive,target}`; the worker replies `complete` (job ID plus exact count) or `hit`/`error`. Logs go to stderr. No HTTP server, socket, Stratum emulation or subprocess-per-chunk restart.

The worker partitions its assigned interval between threads without overlap, searches every in-range scalar exactly once, and reports success only after the full chunk completes. `keypoold` keeps one job in flight and terminates any orphaned child on shutdown/restart; a later multi-machine design can extend the protocol.

## Persistence and recovery

**SQLite, one campaign row** is enough for v1: immutable campaign configuration, `next_i` (next **uncommitted** ordinal), and minimal counters. A single worker completes jobs in ordinal order, so no completed-chunk table, bitmap, lease system or out-of-order watermark is needed.

1. Controller sends job `i=next_i`; state remains unchanged while it runs.
2. On a valid full-completion reply, atomically increment `next_i` in SQLite. Then issue the next job.
3. On interruption, restart from saved `next_i`. At worst, repeat **one** 2^20-key job if its completion was not committed.

`next_i*C` is **verified completed coverage** after worker correctness is established; raw attempts, retries, and speed are separate metrics. Use durable SQLite transactions and a single-instance lock. Never advance progress on a partial result, timeout or unverified worker exit.

## Operation and results

- `systemctl start/stop keypoold`; unit **disabled by default**. Run unprivileged, below normal CPU scheduling priority, with bounded local logs.
- `keypool status` reports campaign ID, completed unique keys/chunks, next job, attempted/replayed work, instantaneous speed and errors. Reading status must not interrupt work.
- On a match, stop dispatch; independently verify the complete compressed SEC1 -> SHA256 -> RIPEMD160 result. Store any recovered secret locally with restrictive permissions, never in routine logs, GitHub or remote APIs.
- The existing `keyhunt` CLI and `-R` remain usable for research. Production mode exclusively takes controller-supplied, strict half-open intervals.
- Check that Puzzle #71 remains unsolved and its public key unavailable before a real long-running session. No BSGS/Kangaroo claim without a known public point.

## Acceptance before production

1. **Coverage:** small exhaustive fixtures verify exact scalar sets, nonoverlapping four-thread partitions, target hits, and no out-of-bounds work, including partial final chunks on generic test intervals. Test permutation bijection on small domains and its mathematical invariants at 50 bits.
2. **Crash safety:** stop/kill controller and worker before, during and after completion/commit. Assert no lost chunk and at most one replayed chunk; reject a mismatched campaign.
3. **Performance:** compare sustained four-core Pi 5 end-to-end unique candidates/s against the validated ~7.34 M/s experimental baseline, including controller overhead. Aim for <5% slowdown; measure rather than assume. Preserve the known-good binary for rollback.

Implementation: [dedicated worker build](../Makefile) gated by `KEYHUNT_POOL_WORKER`, [local seeded SQLite controller](../pool/keypoold.py), [worker protocol tests](../tests/arm64-worker-protocol.py), [crash-replay tests](../tests/keypool-controller.py), [real-worker integration test](../tests/keypool-integration.py), and [manual run instructions](../pool/README.md). These are experimental; **do not** automatically install or enable a service. Physical Pi performance and prolonged recovery validation remain pending.

## Explicitly outside v1

Distributed or untrusted workers, public pool access, proof-of-work challenges, reward sharing, web UI, multiple concurrent campaigns, GPU support, prioritized creator-bias heuristics, subchunk checkpoints and one-row-per-chunk history.

## Supporting research (not implementation requirements)

- [Existing Keyhunt options and search-space audit](../research/2026-10-11-keyhunt-modes-and-search-space.md): upstream `-R` overlaps, bounds, stride, RNG caveats and rejected modes.
- [Pi 5 agent handoff and measurements](AGENT_HANDOFF_PUZZLE71_PI5.md).
- [HonestPool client](https://github.com/homlol/honestpool/blob/main/StartScript.py): work request and completion example; the pool server is not included there.
- [Intel Arc hunter](https://github.com/orfeomorello/Intel-Arc-Puzzle-71/blob/main/tools/hunt.py): seeded Feistel scheduling/checkpoint reference; its single-machine bookkeeping is not a ready-made distributed coordinator.
