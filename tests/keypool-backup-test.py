#!/usr/bin/env python3
"""Keypool backup contract tests. All writes stay in disposable temp dirs."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "production/keypool_backup.py"
spec = importlib.util.spec_from_file_location("keypool_backup", SCRIPT)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def make_campaign(db):
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE campaign(
            id INTEGER PRIMARY KEY, next_i INTEGER,
            inflight INTEGER, found INTEGER, seed TEXT)""")
        conn.execute("INSERT INTO campaign VALUES(1, ?, NULL, 0, ?)",
                     (250, "nonpublic-test-fixture-seed"))
        conn.commit()


def inspect(path):
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        return conn.execute("SELECT next_i,inflight,found,seed FROM campaign").fetchone()


def main():
    with tempfile.TemporaryDirectory(prefix="keypool-backup-tests-") as tmp:
        root = Path(tmp)
        source_dir = root / "source"
        dest_dir = root / "mount"
        source_dir.mkdir()
        dest_dir.mkdir()
        source = source_dir / "campaign.sqlite3"
        make_campaign(source)

        # Fail closed if a mount disappears: do not silently write local backup.
        try:
            backup.create_backup(source, dest_dir, require_rclone=True)
        except RuntimeError as exc:
            assert "active rclone mount" in str(exc), str(exc)
        else:
            raise AssertionError("unmounted destination accepted")
        assert not list(dest_dir.iterdir()), "unexpected local fallback"

        # A live SQLite writer can continue committing while snapshots are made.
        with sqlite3.connect(source) as live:
            for cursor in (251, 252, 253):
                live.execute("UPDATE campaign SET next_i=? WHERE id=1", (cursor,))
                live.commit()
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    result = backup.create_backup(
                        source, dest_dir, keep=2, require_rclone=False)
                assert result["status"] == "ok"
                assert result["completed_chunks"] == cursor
                assert result["sha256"] == backup.checksum(Path(result["file"]))
                assert inspect(Path(result["file"]))[:3] == (cursor, None, 0)
                assert "nonpublic-test-fixture-seed" not in str(result)
                assert "nonpublic-test-fixture-seed" not in out.getvalue()

        snapshots = sorted(dest_dir.glob("keypool-71-*.sqlite3"))
        assert len(snapshots) == 2, snapshots
        assert sorted(inspect(p)[0] for p in snapshots) == [252, 253]
        assert not list(dest_dir.glob("*.partial"))
        assert inspect(source)[0] == 253
        print("PASS: online SQLite snapshot, SHA256, integrity and retention")
        print("PASS: rclone missing-mount guard prevents silent local fallback")
        print("PASS: seed stays absent from status and log output")

        # Installation only creates disabled user units; no Keypool changes.
        config_dir = root / "config"
        tools = root / "admin"
        units = root / "units"
        with mock.patch.multiple(backup, DB=source, CONFIG=config_dir / "backup.json",
                                 TOOLS=tools, UNITS=units,
                                 SCRIPT=tools / "keypool_backup.py",
                                 SERVICE=units / "keypool-backup.service",
                                 TIMER=units / "keypool-backup.timer"):
            with mock.patch.object(backup.subprocess, "run") as system:
                status = backup.install(dest_dir, keep=7, allow_local=True)
                assert status["installed"]
                system.assert_called_once()
                args, kwargs = system.call_args
                assert args[0] == ["systemctl", "--user", "daemon-reload"]
            cfg = json.loads((config_dir / "backup.json").read_text())
            assert cfg == {"destination": str(dest_dir.resolve()), "keep": 7,
                           "require_rclone_mount": False}
            unit = (units / "keypool-backup.service").read_text()
            timer = (units / "keypool-backup.timer").read_text()
            assert "keypool_backup.py run" in unit
            assert "OnCalendar=hourly" in timer and "Persistent=true" in timer
            assert "enable" not in unit and "enable" not in timer
            assert (tools / "keypool_backup.py").is_file()
        print("PASS: opt-in hourly timer installation independent of hunter")


if __name__ == "__main__":
    main()
