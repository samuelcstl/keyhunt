#!/usr/bin/env python3
"""Read-only Keypool progress and liveness snapshot, safe for 5-minute timer."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

DEFAULT_DB = Path.home() / ".local/state/keypool/campaign.sqlite3"
HEALTH = Path.home() / ".local/state/keypool/health.json"
CHUNK = 1 << 20


def read_progress(db):
    if not db.is_file():
        raise RuntimeError("campaign SQLite not found")
    uri = "file:" + quote(str(db.resolve()), safe="/") + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as con:
        row = con.execute(
            "SELECT next_i,inflight,reissued,found FROM campaign WHERE id=1"
        ).fetchone()
    if row is None:
        raise RuntimeError("campaign row missing")
    return dict(zip(("chunks", "inflight", "reissued", "found"), row))


def systemd_active():
    try:
        proc = subprocess.run(["systemctl", "--user", "show",
                               "keypool-hunt.service", "-p", "ActiveState",
                               "--value"], timeout=5, capture_output=True,
                              text=True, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def load_previous():
    try:
        return json.loads(HEALTH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def snapshot(db):
    now = time.time()
    state = read_progress(db)
    previous = load_previous()
    rate = None
    if previous is not None:
        seconds = now - float(previous.get("unix_time", 0))
        previous_cursor = int(previous.get("completed_chunks", -1))
        if 10 <= seconds <= 86400 and state["chunks"] >= previous_cursor >= 0:
            rate = round((state["chunks"] - previous_cursor) * CHUNK /
                         seconds / 1e6, 6)
    return {
        "timestamp_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "unix_time": now,
        "active_state": systemd_active(),
        "completed_chunks": state["chunks"],
        "completed_keys": str(state["chunks"] * CHUNK),
        "inflight": state["inflight"] is not None,
        "recovery_restarts": state["reissued"],
        "found": bool(state["found"]),
        "observed_mkeys_per_second": rate
    }


def write_atomic(data):
    HEALTH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if HEALTH.is_symlink():
        raise RuntimeError("refusing health.json symlink")
    fd, tmp = tempfile.mkstemp(prefix=".health-", suffix=".json",
                              dir=HEALTH.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, HEALTH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    try:
        snap = snapshot(args.db)
        if args.write:
            write_atomic(snap)
        print(json.dumps(snap, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.Error, RuntimeError) as exc:
        print("Keypool health failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
