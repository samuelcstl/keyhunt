#!/usr/bin/env python3
"""Online SQLite snapshots for Keypool, with opt-in hourly user-systemd timer.

Never copies the live .sqlite3 file directly. Uses sqlite3.Connection.backup
to build a consistent local snapshot before publishing on the destination.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import quote
from uuid import uuid4

DB = Path.home() / ".local/state/keypool/campaign.sqlite3"
CONFIG = Path.home() / ".config/keypool/backup.json"
TOOLS = Path.home() / ".local/share/keypool/admin"
UNITS = Path.home() / ".config/systemd/user"
SCRIPT = TOOLS / "keypool_backup.py"
SERVICE = UNITS / "keypool-backup.service"
TIMER = UNITS / "keypool-backup.timer"
DEFAULT_KEEP = 168  # One per hour, seven days of history.


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def atomic_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise RuntimeError("refusing to overwrite symlink: " + str(path))
    fd, temporary = tempfile.mkstemp(prefix=".keypool-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_destination(destination, require_rclone=True):
    # Requiring an existing mount prevents backups silently filling the Pi
    # filesystem if an rclone mount is disconnected or never started.
    if not destination.exists() or not destination.is_dir():
        raise RuntimeError("backup destination must already exist: " + str(destination))
    if destination.is_symlink():
        raise RuntimeError("backup destination symlink not allowed")
    resolved = destination.resolve(strict=True)
    if require_rclone:
        result = subprocess.run(
            ["findmnt", "-T", str(resolved), "-n", "-o", "FSTYPE"],
            capture_output=True, text=True, timeout=10, check=False)
        fstype = result.stdout.strip().lower()
        if result.returncode != 0 or "rclone" not in fstype:
            raise RuntimeError(
                "destination is not under an active rclone mount (found " +
                repr(fstype or "no mount") + "); refusing local fallback")
    if not os.access(resolved, os.W_OK):
        raise RuntimeError("destination is not writable")
    return resolved


def sqlite_snapshot(source_db, output):
    if not source_db.is_file() or source_db.is_symlink():
        raise RuntimeError("existing campaign DB missing or symlink")
    uri = "file:" + quote(str(source_db.resolve()), safe="/") + "?mode=ro"
    # A separate SQLite connection performs an online backup while the
    # controller continues writing. WAL/journal state is included logically.
    reader = sqlite3.connect(uri, uri=True, timeout=30)
    writer = sqlite3.connect(output, timeout=30)
    try:
        reader.execute("PRAGMA busy_timeout=30000")
        reader.backup(writer, pages=128, sleep=0.1)
    finally:
        writer.close()
        reader.close()
    with sqlite3.connect("file:" + quote(str(output), safe="/") + "?mode=ro",
                         uri=True) as snapshot:
        check = snapshot.execute("PRAGMA quick_check").fetchone()
        if not check or check[0] != "ok":
            raise RuntimeError("snapshot quick_check failed")
        row = snapshot.execute(
            "SELECT next_i, inflight, found FROM campaign WHERE id=1").fetchone()
        if row is None:
            raise RuntimeError("snapshot missing campaign cursor")
        if row[1] is not None and row[1] != row[0]:
            raise RuntimeError("snapshot inconsistent in-flight cursor")
        return {"completed_chunks": int(row[0]), "inflight": row[1] is not None,
                "found": bool(row[2])}


def publish_snapshot(local, directory, cursor, keep):
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = "keypool-71-" + now + "-i" + str(cursor) + "-" + uuid4().hex[:8] + ".sqlite3"
    dest = directory / name
    part = directory / ("." + name + ".partial")
    if dest.exists() or part.exists():
        raise RuntimeError("destination backup already exists")
    try:
        with local.open("rb") as inp, part.open("xb") as out:
            shutil.copyfileobj(inp, out, length=1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        original = checksum(local)
        if checksum(part) != original:
            raise RuntimeError("backup transfer hash mismatch")
        os.replace(part, dest)
        if checksum(dest) != original:
            raise RuntimeError("published backup hash mismatch")
        # Only this namespace is eligible for retention cleanup.
        old = sorted(directory.glob("keypool-71-*.sqlite3"))
        if keep > 0:
            for previous in old[:-keep]:
                if previous != dest and previous.is_file() and not previous.is_symlink():
                    previous.unlink()
        return {"file": str(dest), "sha256": original, "bytes": local.stat().st_size}
    finally:
        if part.exists():
            part.unlink()


def create_backup(db, dest, keep=DEFAULT_KEEP, require_rclone=True):
    if keep < 0 or keep > 100000:
        raise RuntimeError("--keep must be in 0..100000 (0 means no pruning)")
    directory = validate_destination(dest, require_rclone=require_rclone)
    # Lock backups only. Do NOT lock the live Keypool controller.
    db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = db.parent / "backup.lock"
    lockfd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another Keypool backup is running") from exc
        with tempfile.TemporaryDirectory(prefix=".keypool-snapshot-", dir=db.parent) as td:
            local = Path(td) / "snapshot.sqlite3"
            state = sqlite_snapshot(db, local)
            transfer = publish_snapshot(local, directory, state["completed_chunks"], keep)
    finally:
        os.close(lockfd)
    return {"status": "ok", **state, **transfer,
            "remote_upload_confirmed": False if require_rclone else None}


def install(destination, keep, allow_local):
    dest = validate_destination(destination, require_rclone=not allow_local)
    if not DB.is_file():
        raise RuntimeError("existing campaign DB missing; never initialize it")
    cfg = {"destination": str(dest), "keep": keep,
           "require_rclone_mount": not allow_local}
    if keep < 0 or keep > 100000:
        raise RuntimeError("invalid retention")
    # Installation is independent of the existing running Keypool service.
    # Units are deliberately not started/enabled by this command.
    TOOLS.mkdir(parents=True, exist_ok=True, mode=0o700)
    if SCRIPT.resolve() != Path(__file__).resolve():
        shutil.copyfile(__file__, SCRIPT)
        os.chmod(SCRIPT, 0o600)
    atomic_text(CONFIG, json.dumps(cfg, indent=2) + "\n")
    atomic_text(SERVICE, """[Unit]
Description=Keypool online SQLite backup

[Service]
Type=oneshot
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/python3 %h/.local/share/keypool/admin/keypool_backup.py run
""")
    atomic_text(TIMER, """[Unit]
Description=Hourly Keypool SQLite backup

[Timer]
OnCalendar=hourly
Persistent=true
AccuracySec=1min
Unit=keypool-backup.service

[Install]
WantedBy=timers.target
""")
    subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=10, check=True)
    return {"installed": True, "destination": str(dest), "keep": keep,
            "timer": "keypool-backup.timer (disabled until enabled)"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "run"))
    parser.add_argument("--dest", type=Path, help="Existing backup destination directory")
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--keep", type=int, default=None,
                        help="Number of hourly snapshots to retain, default 168; 0=unlimited")
    parser.add_argument("--allow-local", action="store_true",
                        help="Explicitly allow a local/non-rclone destination")
    args = parser.parse_args()
    try:
        if args.action == "install":
            if args.db != DB:
                raise RuntimeError("installation uses the existing default campaign DB")
            if args.dest is None:
                raise RuntimeError("install requires --dest")
            result = install(args.dest, args.keep if args.keep is not None
                             else DEFAULT_KEEP, args.allow_local)
        else:
            if args.dest is None:
                cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
                destination = Path(cfg["destination"])
                keep = args.keep if args.keep is not None else int(cfg["keep"])
                require_rclone = bool(cfg["require_rclone_mount"])
            else:
                destination = args.dest
                keep = args.keep if args.keep is not None else DEFAULT_KEEP
                require_rclone = not args.allow_local
            result = create_backup(args.db, destination, keep, require_rclone)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError,
            sqlite3.Error, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print("Keypool backup FAILED: " + str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
