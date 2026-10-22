# Pi 5 Keypool Puzzle 71: controlled 24/7 deployment

This is a production **proposal**. The GitHub PR itself must not activate
anything. Preserve Bitcoin Core and ckpool services that feed the NerdQaxe:
**no changes to the BTC node, ckpool, ports or network configuration**.

## Selection and invariants

- **Initial worker:** `keyhunt-worker-r7-ecc-fold-unprofiled`,
  because the final Pi5 four-way test showed no convincing difference
  from R7-PAIR and R7-FOLD has a longer independent qualification.
- Alternatives installed alongside it:
  `keyhunt-worker-r7-ecc-pair-unprofiled` and
  `keyhunt-worker-r3-ecc-sched`. Reversible release selection is explicit.
- The existing Keypool campaign at
  `~/.local/state/keypool/campaign.sqlite3` is the single source
  of truth. **Never run `pool/keypoold.py init` on that path**.
  Never import a benchmark or test campaign's synthetic seed.
- The 24/7 service is **disabled by default** and never started by
  the installer or a GitHub merge.
- Default controller is unchanged: `pool/keypoold.py run --worker`
  with unlimited jobs (`--max-jobs 0`), four worker threads and
  four speculative jobs (`--window 4`).
- A startup preflight validates existing DB target, bounds,
  chunk size, seed syntax, cursor, original target file and
  expected SHA256s for the *copied* controller and worker.
  If any mismatch exists or `found=1`, service startup refuses.
- `flock` in the existing Keypool controller prevents two
  controllers owning this campaign. Do not run another unmanaged
  `keypoold.py run` concurrently.
- CPU limited to **150% total by default** (adjustable from 50–200% at install), `Nice=10`, with Bitcoin Core and
  ckpool left running. `Restart=on-failure`, not `Restart=always`,
  so a successful verified hit stops without a busy restart loop.
- systemd uses `KillMode=mixed`: SIGTERM goes to the Python
  controller **before** the C++ worker. The controller stops dispatch,
  drains already-sent jobs, and commits the cursor while the child remains
  alive. After `TimeoutStopSec=120s`, systemd may forcibly terminate the
  remaining cgroup if draining hangs. A forced stop or power loss can replay
  at most the bounded uncommitted window; already committed chunks remain
  durable.
- Physical stop regression, 22 October 2026: initial 90-second smoke reached
  cursor 770 from 520 at 150% total CPU (52.35 C, throttled=0), but the
  prior `KillMode=control-group` terminated the child and left
  `inflight=770`. The next safe startup is expected to reissue unfinished
  work; **never edit SQLite manually**. Re-test controlled stop with this
  corrected unit before enabling persistent operation.

## Deployment (only after PR reviewed and merged)

Use the normal Pi5 login `pi5claw`, **not root**, and a dedicated
clean production worktree:

```bash
BASE="$HOME/BITCOIN_ANALYSIS/bitcoin-puzzle"
git -C "$BASE/keyhunt" fetch origin main
git -C "$BASE/keyhunt" worktree add --detach "$BASE/keyhunt-prod" origin/main
cd "$BASE/keyhunt-prod"

# Read-only check of existing campaign progress:
python3 pool/keypoold.py status

# Build and validate approved binaries, verify existing campaign,
# stage immutable SHA256-manifested release; install DISABLED units:
python3 production/install_keypool.py
# Optional when the BTC node needs more headroom: --cpu-quota 125
```

If `keyhunt-prod` already exists, **do not delete or reset it**.
Review its status and update the existing worktree carefully instead.

Installation creates:
- `~/.local/share/keypool/releases/<commit>-<sha>/`, holding copied
  controller, three distinct validated workers, preflight, health
  collector and `release-manifest.json`;
- atomic `~/.local/share/keypool/current` symlink to that immutable
  release; deployment refuses if the installed user service is active
  or enabled;
- `~/.config/systemd/user/keypool-hunt.service` and
  `keypool-health.{service,timer}`, **not enabled**.

The installer never initializes, migrates, re-permutes, resets or
advances production SQLite. It runs the existing Puzzle20 worker
oracle and crash/replay tests **only against temporary fixture DBs**
before writing the installed release.

## Deliberate initial smoke, then 24/7 activation

Verify the exact installed artifact and proposed service:

```bash
systemctl --user cat keypool-hunt.service
python3 "$HOME/.local/share/keypool/current/keypool_preflight.py" \
  --db "$HOME/.local/state/keypool/campaign.sqlite3" \
  --worker keyhunt-worker-r7-ecc-fold-unprofiled
systemctl --user is-enabled keypool-hunt.service || true

# Manual smoke, on the existing campaign (actual new search coverage):
systemctl --user start keypool-hunt.service
systemctl --user status --no-pager keypool-hunt.service
python3 "$HOME/.local/share/keypool/current/keypool_health.py"
# Review progress; stop gracefully before checking cursor:
systemctl --user stop keypool-hunt.service
python3 pool/keypoold.py status
```

Once this smoke and the miner's BTC/ckpool performance are acceptable,
**explicitly authorize boot persistence**:

```bash
# Needed only once on Pi OS if user systemd should survive logout/reboot.
# Requires sudo: this is NOT invoked by the installer.
sudo loginctl enable-linger pi5claw

systemctl --user enable --now keypool-hunt.service
systemctl --user enable --now keypool-health.timer
```

Verify:

```bash
systemctl --user show keypool-hunt.service -p ActiveState -p CPUQuotaPerSecUSec
systemctl --user list-timers keypool-health.timer
journalctl --user -u keypool-hunt.service -n 30 --no-pager
cat "$HOME/.local/state/keypool/health.json"
python3 pool/keypoold.py status
```

The health snapshot is written every five minutes to owner-only
`~/.local/state/keypool/health.json`. It reports controller service
state, completed chunks/keys, restart counter, in-flight flag, whether
a verified hit has been recorded, and observed keys/s since the last
sample, Pi CPU temperature where available, Raspberry Pi under-voltage/throttling
flags where `vcgencmd` exists, and the number of seconds since the cursor
last advanced. A stalled running service is flagged after 15 minutes
(`stall_suspected=true`); a missing sensor is reported as `null`, not
silently interpreted as healthy. It **never reports the secret scalar or
campaign seed**. The first snapshot has no throughput baseline.
The health timer records status locally; it does not send push alerts.

## Stop, rollback, recovery

```bash
systemctl --user disable --now keypool-hunt.service keypool-health.timer
python3 pool/keypoold.py status
```

To change the 150% total CPU quota, stop and disable the service,
then reinstall with e.g. `python3 production/install_keypool.py
--cpu-quota 125`; the installer validates the allowed 50–200% range.
All three worker binaries remain separately SHA256-pinned.

To select R7-PAIR or fall back to R3, stop and disable the service
first, then run `python3 production/install_keypool.py --worker
keyhunt-worker-r7-ecc-pair-unprofiled` (or `...r3-ecc-sched`).
The installer stages a new versioned release, **never overwrites
the previous release or SQLite**. Recheck the unit and hashes, perform
a manual smoke, then enable again if appropriate.

Do not remove the old release until rollback and restart behavior
have been verified. Do not delete the SQLite `.lock` file or
`inflight` reservation: the controller itself handles safe recovery.
Never upload or publicly paste `FOUND.private`.

## Honest performance expectation

The 21 October final used four balanced rounds at `CPUQuota=150%`.
R7-FOLD averaged **2.891 M completed Puzzle71 candidates/second**
(against 2.897 M for R7-PAIR and 2.876 M for R3-SCHED).
This rate is workload-dependent: Bitcoin Core initial catch-up may
temporarily use significant CPU; 24/7 monitoring should check that
both the BTC node and Keypool remain healthy, not merely that the
worker reports a large throughput value.

There is no predictable near-term discovery time for Puzzle71 at this
rate. The goal of this PR is to deliver **real durable coverage,
safely and continuously**, not to imply a breakthrough in the
underlying search-space difficulty.
