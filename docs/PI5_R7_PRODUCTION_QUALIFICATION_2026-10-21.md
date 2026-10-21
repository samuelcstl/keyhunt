# Pi 5 R3-SCHED vs R7-FOLD promotion gate (21 Oct 2026)

Experimental qualification only. No service is installed or enabled. No changes
to Keypool's live Puzzle 71 SQLite seed or cursor.

## Why this gate

Historical 18-Oct-2026 R3 head-to-head: SCHED won 7/8 trials against NEON.
The R7-FOLD 24-job, 2-pair screen had +8.28% and +0.23% against R3,
with a conspicuously slow first R3 control (6.815 Mkeys/s). The claimed
+4.25% median is insufficient for production promotion. R9/R10 also
underperformed the ~7.3M four-core worker; do not substitute their
standalone pipelines for the actual production worker.

R3-SCHED includes R1 changes, R2-SRI RIPEMD160, and R3 ECC scheduling.
R7-FOLD keeps that foundation and tests paired full-point computation.

## Use one isolated Pi worktree

```bash
BASE="$HOME/BITCOIN_ANALYSIS/bitcoin-puzzle"
git -C "$BASE/keyhunt" fetch origin test/pi5-r7-promotion-gate-20261021
git -C "$BASE/keyhunt" worktree add --detach "$BASE/keyhunt-r7-qual" origin/test/pi5-r7-promotion-gate-20261021
cd "$BASE/keyhunt-r7-qual"
```

Never run `pool/keypoold.py init` against the existing campaign.

### Gate 1: sustained full worker protocol

```bash
bash tests/arm64-r7-promotion-gate.sh worker
```

Build + correctness gates, then **256 completed 2^20-key chunks per
observation**, six reversed-order pairs. Uses identical scratch Feistel
chunk order and exactly four worker threads. Runtime stage tracing disabled.
Logs preserve source, ELF binaries, SHA256, disassembly, CPU state,
temperature and raw per-pair rates.

### Gate 2: *genuine* production-controller SQLite at a 150% total CPU quota

Run Gate 1 first to build both binaries:

```bash
systemd-run --user --scope -p CPUQuota=150% -- bash tests/arm64-r7-promotion-gate.sh sqlite
```

If the user's systemd manager is unavailable, STOP and investigate; do not
silently rerun without a quota. The script reads its cgroup v2
`cpu.max` and fails unless quota is between 140%-150%.

Gate 2 runs the **real** `pool/keypoold.py run --worker ...` for each
worker, 128 chunks and four reversed-order pairs, with a fresh privately
stored SQLite DB per observation. Each test DB gets the same test-only
Feistel seed, same Puzzle 71 public target and bounds. Committed cursor
must equal its dispatched job count with no remaining in-flight work or
restarts. Every run measures completed unique key candidates per elapsed
wall time, including controller startup and SQLite transactions.

All artifacts are under `../runs/arm64-r7-promotion/`. The EXIT trap
creates a full `$HOME/r7-promotion-results-<run-id>.tar.gz` with checksums,
including on failure; if a private hit is detected, archiving is suppressed.
Keep such a case entirely local and private.

## Promotion criteria

Do not promote a compiler microbenchmark gain alone. Look for a consistent
worker win in Gate 1, stable Pi clock/no throttling and a similarly positive
SQLite Gate 2 result at the intended CPU quota. Reject unrepeatable or
low-effect results, or repeat only focused matching pairs when evidence is
borderline. If R7 fails, retain R3-SCHED as the promotion candidate.

Before the service is enabled: validate restart/crash-replay using the selected
worker, maintain immutable campaign parameters and explicitly select the binary
with `pool/keypoold.py run --worker /absolute/path/to/validated/worker`.
Never change the main campaign's DB for benchmarking.
