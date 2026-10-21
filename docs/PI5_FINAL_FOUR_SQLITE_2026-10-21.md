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
