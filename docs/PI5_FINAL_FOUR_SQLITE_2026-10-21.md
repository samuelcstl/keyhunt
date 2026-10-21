# Pi 5 four-worker finale, October 21 2026

**Purpose:** a single useful 10–15-minute (target) final qualification
after reboot, with **Bitcoin Core + ckpool left active** so that NerdQaxe
continues uninterrupted. This is NOT intended to benchmark every R1–R10
microbenchmark again.

## The final four

1. R3-SCHED, `keyhunt-worker-r3-ecc-sched` (historic reference)
2. R7-PAIR-OFF, `keyhunt-worker-r7-ecc-pair-unprofiled`
3. R7-FOLD-OFF, `keyhunt-worker-r7-ecc-fold-unprofiled`
4. R2-SRI, `keyhunt-worker-r2-ripemd-sri`

All four speak the same Keypool JSON worker protocol, generate the same
Puzzle71 range for the same synthetic Feistel seed, and have independent
crypto/coverage and restart fixture tests. Zero R7 profiler clocks are
compiled into the chosen R7 binaries.

## Pi setup

After reboot, allow the Bitcoin node to finish any catch-up or startup
resource spike. **Do not stop Bitcoin Core or ckpool for the benchmark**.
Ensure the *old Keypool background benchmark or campaign worker itself*
is not running; do not alter its SQLite database.

Reuse the already compiled catalog worktree, avoiding a lengthy clean build:

```bash
BASE="$HOME/BITCOIN_ANALYSIS/bitcoin-puzzle"
WT="$BASE/keyhunt-variant-catalog"
git -C "$WT" status --short
git -C "$WT" fetch origin test/pi5-four-worker-final-20261021
git -C "$WT" switch --detach FETCH_HEAD
cd "$WT"
python3 tests/arm64-four-worker-sqlite-final.py --selftest
```

A modified tracked file blocks the actual benchmark. There is no forced reset,
no `git clean`, no service change, and no checkout of the active Keypool
worktree. The only build targets are the four final worker executables.

Start the CPU-limited final explicitly:

```bash
systemd-run --user --scope -p CPUQuota=150% -- \
  bash tests/arm64-four-worker-sqlite-final.sh
```

The runner reads its **actual cgroup v2 `cpu.max`** and rejects any
missing/wrong CPU quota before executing the measured rounds.

## Protocol and duration

- Four rounds × four workers, **96 chunks per worker/round**
  (100,663,296 completed candidates per observation), four prefetched
  chunks and full SQLite checkpointing. Sixteen measured observations.
- Each worker gets one position in every round. The exact sequence is:
  - R3, R7-PAIR, R7-FOLD, R2
  - R2, R7-FOLD, R7-PAIR, R3
  - R7-PAIR, R2, R3, R7-FOLD
  - R7-FOLD, R3, R2, R7-PAIR
- Four small eight-chunk warmups, excluded from the reported rankings.
- `keypoold.py run` runs with `--worker` set to one of the four
  full-ELF SHA256-pinned finalists and `--db` pointed at a **brand-new**
  `campaign.sqlite3` in the local evidence directory. Identical
  deterministic test-only seed; never the user's live campaign seed.
- Every observation checks `PRAGMA quick_check=ok`, cursor=96,
  no in-flight reservation/reissued work, and `found=0`.
- Sample clock, Pi temperature, throttling before/after, CPU quota
  and process list. Include actual source commit and all worker SHA256s.
- Expected: roughly 9–12 minutes on a reasonably idle Pi5 under
  CPUQuota=150%. Runtime varies with blockchain node load.
  A strict 960-second global measure budget and 180-second per-observation
  timeout prevent an unattended multi-hour exercise; build has a separate
  240-second cap if any compiled target is stale or missing.
- The exited runner automatically creates
  `$HOME/four-worker-final-results-<run>.tar.gz` with checksums.
  A real verified hit suppresses archiving; keep any `FOUND.private`
  locally and never upload it.

## Interpretation

Use **same-round rate ratios vs R3** plus all six pairwise comparisons
and 4-round median/mean. Each engine occupies each test slot once,
reducing order bias. Because these comparisons use only four rounds
and there are still active blockchain services, small margins should
not be promoted without checking drift, throttling, run variability and
the already recorded earlier R7-FOLD qualification.

The previous R7-FOLD real SQLite +150% CPU result showed a positive
median (+1.42% with 3/4 wins) and remains independent evidence.
We are specifically testing whether R7-PAIR or R2-SRI beats R7-FOLD
for the same intended CPU quota. No change is made to the current
systemd services or the production worker.

## Final physical evidence: 21 October 2026

**Result:** completed at 2026-10-21T15:26:50Z, measured wall
time **573.4 s** including warmups. Evidence from
`four-worker-final-results-20261021T151713Z-29832.tar.gz`,
archive SHA256
`d94d133661f291e59944a8024a36420118ceae9a17db80bfa759eb571bdb580c`.
Source commit `ccd612348e2adfc1ee9e41a18779d58c74cc3fec`.
Archive manifest **123/123 SHA256 checks pass**; exact four ELF hashes
also match `observations/provenance.json`.

The real cgroup v2 quota was **`150000/100000` (150% total CPU)**.
All 20 scratch databases (4 warmups + 16 measured) passed
`PRAGMA quick_check`, used identical seed
`0f1e2d3c4b5a69788796a5b4c3d2e1f0`, had the expected
8/96 committed chunks, no in-flight reservation or reissued work
and `found=0`. The real campaign file's size and mtime
were identical before and after the run; the live DB was not opened
by this benchmark. Each of the 16 measured observations re-scanned
**the same** 100,663,296 candidate keys for a controlled A/B, so
the 1,610,612,736 candidate evaluations must not be counted as
that many globally distinct new keys in Puzzle 71.

All temperatures sampled 47.7–55.4 °C, ARM clock ~2.4 GHz,
`throttled=0x0`. Core blockchain services remained active;
the before-process snapshot showed bitcoind using substantial CPU
(~29%), falling to ~7% after the run, a plausible source of noise.

### Complete measured SQLite throughput

All rates below include controller startup and SQLite commits.
Four balanced measured rounds, 96 × 2^20 candidates per observation.

| Worker | Round 1 | Round 2 | Round 3 | Round 4 | Mean Mkeys/s |
|---|---:|---:|---:|---:|---:|
| R7-PAIR-OFF | 2.913558 | 2.871220 | 2.892097 | 2.912963 | **2.897459** |
| R7-FOLD-OFF | 2.904501 | 2.908834 | 2.887842 | 2.863193 | **2.891093** |
| R3-SCHED | 2.881276 | 2.871204 | 2.827169 | 2.925606 | 2.876314 |
| R2-SRI | 2.838935 | 2.879408 | 2.823108 | 2.847248 | 2.847175 |

Matched-round median advantage relative to R3:
R7-PAIR **+0.560% (3/4 wins)**, R7-FOLD **+1.058% (3/4)**,
R2-SRI **−0.807% (1/4)**. R7-PAIR beats R7-FOLD **3/4**,
with only **+0.230% paired median** (mean throughput difference
about +0.220%). These margins are comparable to run-to-run noise.

R7-FOLD additionally has earlier sustained head-to-head
(6/6 wins vs R3, +0.614% median) and independent
scratch SQLite 150%-CPU gate (3/4, +1.422% median).
That independent evidence makes **R7-FOLD-OFF the conservative
initial production candidate**, with R7-PAIR retained as a
close interchangeable alternative. No further broad
benchmarks are justified before starting the carefully monitored
service: the difference between the two is negligible in practice.

### Deployment caveats

The PRs #13, #14 and #15 containing the experimental catalog and final
benchmark tools are **already merged into the fork's `main`** as of
2026-10-21 15:47 UTC. This physical evidence has not, by itself,
activated a Keypool service or changed the production worker.
An operations PR should pin the selected ELF SHA256/commit,
keep a simple `--worker` rollback path, log persistent campaign
cursor and validated chunks, enforce lower CPU scheduling priority
with a configurable ~150%-CPU quota, and leave the service disabled
on boot until explicitly approved.

Exact ELF SHA256:
- R7-FOLD-OFF:
  `603133623f8a9aaa841041ccad40626f8f2a33308c381a8cf8ed7e75206ef959`
- R7-PAIR-OFF:
  `fddf6f994cf0b77558d415ca45c70375350289252a8f7bfd11653c6bf307243e`
- R3-SCHED:
  `31efdb2fe3ada3b6c23a230dae8fc04b87681dfffb2a4b9c5881b1557d7d6475`
- R2-SRI:
  `de591aab7aa5b7a7cb649dbc23795f71f2ef68c82214d6cb2e9ca5748cad4088`
