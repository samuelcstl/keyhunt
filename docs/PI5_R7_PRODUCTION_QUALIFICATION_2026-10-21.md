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


## Physical Gate 2 result: real scratch SQLite at 150% CPU, 21 Oct 2026

- Evidence: `r7-promotion-results-20261021T125647Z-2342244-sqlite.tar.gz`.
- Full TAR SHA256: `b4cd1ceb1fe913eacb72a3ddb5235ed57aa883375cd0fa53778aae8356dc187f`.
- Tested commit `edd3d5f70eb7cc2a8d6916369db0c27936659d6d`, which includes
  the earlier fix to select the truly unprofiled R7-FOLD binary for SQLite.
- Archive integrity: **66/66 SHA256SUMS entries PASS**. Both ELF binary
  hashes match provenance:
  R3 `41b1928432857aee292470d0de39db819f9aa605d7177d71dc9bff6774c62580`,
  R7 unprofiled `95c86342b833cd81627f672fe68552bfdd8d9ca6e1cb51b1da7187033e410499`.
  Neither archived ELF has an `R7_STAGES worker=` marker.
- CPU quota: actual cgroup v2 `cpu.max=150000 100000`,
  corresponding to 1.5 CPU cores in total; sampled ARM clock ~2.4 GHz,
  temperatures 47.7–56.5 C, `throttled=0x0`.
- **Four alternating control/candidate pairs**, each observation completes
  **128 × 2^20 = 134,217,728** cryptographically processed Puzzle 71
  candidates and commits 128 chunks to a *separate scratch SQLite DB*.
  The same deterministic test Feistel seed is used in all 8 databases
  so each paired worker scans the same chunks; those chunks are
  intentionally repeated **across** measurements (do not sum them as
  global unique search coverage).
- R3-SCHED recorded 2.925651, 2.902425, 2.895850, 2.897367 Mkeys/s;
  mean **2.905323 Mkeys/s**.
- R7-FOLD unprofiled recorded 2.910503, 2.954489, 2.952034,
  2.927778 Mkeys/s; mean **2.936201 Mkeys/s**.
- Matched effects in order: **−0.5178%, +1.7938%, +1.9402%, +1.0496%**;
  **3/4 wins**, paired median **+1.4217%**, paired mean +1.0665%.
- Independent post-extraction SQLite inspection: all **8/8 PRAGMA quick_check
  `ok`**; each campaign row has identical test seed,
  `next_i=128`, `inflight=NULL`, `reissued=0`, `found=0`.
  Each controller log confirms `Completed 128 jobs ... cursor=128`.
  The default user's Puzzle 71 campaign was not opened by the scripted
  diagnostic path. A direct live-before/live-after DB snapshot was not
  performed and is **not** claimed.
- Background blockchain nodes, pools and Chromium were running. There are
  only four paired repeats; the effect is small and noisy, so do not
  represent this as a high-confidence universal 1.42% performance gain.

**Engineering disposition:** R7-FOLD-unprofiled has passed the intended
directional promotion gates against R3-SCHED: real four-core worker
(+0.614% paired median, 6/6) and scratch SQLite with real controller at
150% total CPU (+1.422% median, 3/4). Prefer R7-FOLD for an **isolated
candidate integration PR**, but **do not merge the stacked experimental R6/R7
branches or switch the real campaign yet**. Create a clean, minimal promotion
diff on top of our fork's `main` (PR #1 was merged separately), re-run
ARM64 CI/Puzzle20 and a short physical smoke of the exact newly linked
binary, and retain R3/production rollback. Before unattended operation,
complete explicit stop/kill/restart tests of the promoted artifact and
keep the systemd service disabled by default.

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
