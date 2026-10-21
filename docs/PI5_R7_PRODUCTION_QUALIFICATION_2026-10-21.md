# Pi 5 R3-SCHED vs R7-FOLD promotion gate (21 Oct 2026)

Experimental qualification only. No service is installed or enabled. No changes
to Keypool's live Puzzle 71 SQLite seed or cursor.

## Why this gate

**Correction after the first Gate 1 run on 21 Oct:** its R7-FOLD executable was
compiled with `KEYHUNT_R7_STAGE_STATS`. Passing
`KEYHUNT_R7_STAGE_PROFILE=0` did **not** disable stage timing because
the code checks only whether `getenv()` returns a pointer. The
six 256-chunk paired comparisons yielded R7-FOLD −0.052% median (2/6 wins);
that is valid for the instrumented executable, but not a fair promotion test.
The updated gate builds and validates the separate
`keyhunt-worker-r7-ecc-fold-unprofiled` target, completely excluding
per-batch stage timestamps and counters at compile time.
The qualification refuses any candidate binary containing the R7 stage
logging marker. **Re-run Gate 1 on the corrected branch.**

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
chunk order and exactly four worker threads. R7-FOLD stage tracing entirely absent from the timed executable.
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

## Physical Gate 1 result: uninstrumented Pi worker, 21 Oct 2026

- Evidence: `r7-promotion-results-20261021T122540Z-2266739-worker.tar.gz`
  (user-side copy may carry a local `(1)` suffix).
- Uploaded TAR SHA256: `8f9f514b93f50ead6f234f493d2a280b2ec82db4f815c91a0ac981cea5689410`.
- Tested commit: `4a0d368f86be88e703a1f7bf862543e571f436de`.
- Archive integrity: **38/38 SHA256SUMS entries PASS**; both compiled ELF
  worker digests match the recorded manifest. The unprofiled R7 binary has
  no `R7_STAGES` marker. Worker protocol, Puzzle20 cryptographic fixtures,
  exhaustive coverage and crash replay all PASS.
- Six reversed pairs, each executable performing 268,435,456 distinct
  diagnostic candidates (1,610,612,736 per worker):
  R3-SCHED mean 7.148630 Mkeys/s; **R7-FOLD unprofiled mean 7.208112
  Mkeys/s**. Paired improvements, in order: +0.2452%, +0.2779%, +2.1248%,
  +1.1481%, +0.2616%, +0.9507%.
  **6/6 wins**, paired median **+0.6143%**, paired mean +0.8347%.
- Before/after Pi ARM clock samples ~2.4 GHz, `throttled=0x0`, sampled
  temperature from 52.1 to 65.3 C. Other nodes/daemons were active;
  no CPU isolation, per-core PMU or robust power study.
- **Interpretation:** promising small repeatable improvement, sufficient to
  advance to quota-limited scratch SQLite Gate 2. NOT permission to merge
  as the production worker yet. Broad confidence intervals and external
  load can affect this sub-1% gain.

**Critical runner fix made after Gate 1:** the archived script's `sqlite`
mode still named the *profiled* `keyhunt-worker-r7-ecc-fold`, even though
Gate 1 correctly used the `-unprofiled` binary. PR #12 now uses the
unprofiled candidate in **both** modes and has a CI guard preventing this
regression. Fetch the latest qualification branch before Gate 2.

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
