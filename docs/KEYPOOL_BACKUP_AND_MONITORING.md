# Keypool monitoring and online SQLite backups

This component is independent of the Bitcoin Puzzle 71 search worker. It
does not stop, rebuild, or redeploy the running Keypool service.

## Status commands

Campaign state and committed progress:

    python3 ~/.local/share/keypool/current/keypoold.py status

Service state, latest throughput, temperature and throttling:

    systemctl --user status keypool-hunt.service --no-pager
    python3 ~/.local/share/keypool/current/keypool_health.py
    cat ~/.local/state/keypool/health.json

The existing keypool-health.timer writes a new health snapshot every five
minutes when enabled.

## Readable one-command status

The standalone CLI displays progress and health and provides explicit
start/stop control through the existing systemd user unit. It lives in
~/.local/bin and follows the existing ~/.local/share/keypool/current symlink.
**Installing the CLI does not touch or restart the running hunter.**

From the updated repository checkout:

    mkdir -p ~/.local/bin
    install -m 755 production/keypool_cli.py ~/.local/bin/keypool

Available commands:

    keypool                  # readable total coverage, current rate and next milestone
    keypool status           # same readable summary
    keypool health           # summary + inflight, recovery and stall details
    keypool logs             # last 40 systemd journal entries
    keypool start            # start service and enable at boot
    keypool stop             # graceful stop and disable at boot
    keypool --json           # original campaign JSON for scripts
    keypool health --json    # original health JSON for scripts

The `start` command runs `systemctl --user enable --now keypool-hunt.service`;
`stop` runs `systemctl --user disable --now keypool-hunt.service`. The
CLI verifies the resulting systemd active state and returns a nonzero exit
code on failures. Only the hunt unit is changed; the health and off-device
backup timers are independent. The existing service uses `KillMode=mixed`
for a controlled stop and replays unfinished jobs on the next start.
These commands do **not** create, migrate, reset or rewrite SQLite directly.
The service preflight still refuses startup when a verified hit already exists
or campaign/release validation fails. `--json` is available for status/health
only.

The progress bar deliberately describes the **next key-count milestone**
(100 billion, then one trillion, etc.), not total keyspace coverage.
The exact full-interval percentage is shown on a separate line so the
visual never misrepresents search progress. Remaining time to the next
milestone is conditional on the latest measured speed, not a guaranteed
ETA for finding a private key.

## One-shot online SQLite backup

The script uses sqlite3.Connection.backup() to take a consistent SQLite
snapshot while the worker continues running. It checks PRAGMA quick_check,
copies a local temporary snapshot to a unique UTC-and-cursor-named file in
the destination, verifies SHA256, and publishes it by renaming the staged
destination file. It never directly copies or changes the live DB.

Provide an existing directory under your own rclone mount. For example:

    DEST="/path/to/rclone-mount/keypool-backups"
    findmnt -T "$DEST" -o TARGET,FSTYPE,SOURCE

    # Run from a checkout of the repository:
    python3 production/keypool_backup.py run --dest "$DEST"

The backup refuses a missing or unmounted destination. It specifically
requires a live rclone mount (fuse.rclone), including when the configured
directory is a subdirectory of the mountpoint. This avoids silently using
local Pi storage when the network mount disappears.

For intentional local backups only, use the explicit --allow-local switch.

## Install independent hourly backup timer

This creates an independent script and two user-systemd units, disabled
until you activate the timer. It does not modify keypool-hunt.service.

    DEST="/path/to/rclone-mount/keypool-backups"
    python3 production/keypool_backup.py install --dest "$DEST" --keep 168

    # Perform the first backup and see the result:
    systemctl --user start keypool-backup.service
    journalctl --user -u keypool-backup.service -n 15 --no-pager

    # Then schedule hourly snapshots:
    systemctl --user enable --now keypool-backup.timer

    # Later, inspect schedule and any failures:
    systemctl --user list-timers keypool-backup.timer --no-pager
    journalctl --user -u keypool-backup.service -n 20 --no-pager

Config is stored as a mode-0600 JSON file at
~/.config/keypool/backup.json. The installer copies the backup script to
~/.local/share/keypool/admin/keypool_backup.py and does not reinstall or
replace the active immutable Keypool worker release.

By default, the newest 168 snapshots are kept (one per hour for seven days).
Older backups matching keypool-71-*.sqlite3 in that exact backup directory
are pruned only after a new snapshot is successfully published and checked.
Use --keep 0 to disable rotation.

Disable automatic backups with:

    systemctl --user disable --now keypool-backup.timer

## Verified-win persistence (no live database migration)

A correctly verified win is saved to `FOUND.private` and to the same SQLite
campaign file. On the first verified win only, the controller creates a
`verified_hit` table and atomically commits the private key
(`private_key_hex`), completed job ordinal (`job_index`), and
`campaign.found=1` with the progress cursor. A crash before that
transaction commits leaves the job uncommitted and therefore replayable.

**Existing Puzzle 71 campaigns need no schema migration.** The controller
does not alter their tables, scheduling seed, chunk order, or cursor before a
verified hit. Keep the normal `keypool` and `keypool --json` status output
free of secrets. The `verified_hit` row itself contains a secret; avoid
printing it in a terminal, chat, or CI log.

An SQLite snapshot made *after* the verified-hit transaction includes the
winning key. An earlier snapshot can only resume its recorded progress; it
cannot prove the win occurred later. Existing periodic off-device backups
do not guarantee an immediate post-win copy.

**Security warning:** off-device SQLite backups can now contain a spendable
Bitcoin private key. Use a separately encrypted storage destination (e.g.
rclone crypt), protect the backup directory and retention copies, and never
upload database snapshots to public repositories or paste their contents.

## Notes and limitations

- Protect all SQLite backups. Prior to a win they contain the private
  scheduling seed; after a win they also include the winning private key.
  The separate FOUND.private file is NOT part of this backup.
- rclone mounts can cache successful writes locally. A readable backup and
  matching SHA256 on the mount do NOT prove Google Drive has completed its
  remote upload. For strict durability, verify the corresponding object using
  the configured rclone remote after the mount's write-back delay.
- If rclone is unmounted at backup time, the job fails loudly. The next timer
  invocation retries; it never falls back to the local Pi directory.
- Restoring is deliberately manual and requires stopping Keypool first.
  Do not manually replace the live database while Keypool is active.
