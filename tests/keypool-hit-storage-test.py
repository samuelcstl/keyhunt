#!/usr/bin/env python3
"""Regression: a verified hit survives loss of FOUND.private via SQLite.

Entirely isolated solved-Puzzle-20 fixture with a fake protocol worker.
Does not inspect or mutate the user's production campaign.
"""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("keypoold", ROOT / "pool/keypoold.py")
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)
KEY = 0xD2C55


def main():
    with tempfile.TemporaryDirectory(prefix="keypool-hit-storage-") as tmp:
        folder = Path(tmp)
        db = folder / "campaign.sqlite3"
        target = folder / "target.txt"
        worker = folder / "fake-worker.py"
        target.write_text(pool.FIXTURE_TARGET + "\n", encoding="ascii")
        pool.init(db, target, fixture=True)
        with pool.connect(db) as conn:
            original = pool.load(conn)
            assert original["next_i"] == 0 and original["found"] == 0
            assert conn.execute(
                "SELECT count(*) FROM sqlite_master "
                "WHERE type='table' AND name='verified_hit'"
            ).fetchone()[0] == 0, "Migration must be lazy"

        worker.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "key = 0xD2C55\n"
            "for line in sys.stdin:\n"
            "    job = json.loads(line)\n"
            "    lo = int(job['start'], 16)\n"
            "    hi = int(job['end_exclusive'], 16)\n"
            "    count = hi - lo\n"
            "    if lo <= key < hi:\n"
            "        result = dict(type='hit', id=job['id'], count=count, key=hex(key))\n"
            "    else:\n"
            "        result = dict(type='complete', id=job['id'], count=count)\n"
            "    print(json.dumps(result), flush=True)\n",
            encoding="ascii",
        )
        worker.chmod(0o700)

        # The matching file is fsync'ed before this deliberate pre-commit
        # failure. Both the key record and found flag must remain uncommitted.
        os.environ["KEYPOOL_TEST_INTERRUPT_BEFORE_COMMIT"] = "63"
        try:
            try:
                pool.run(db, worker, max_jobs=0, timeout=30, window=4)
            except RuntimeError as err:
                assert "Injected fixture crash" in str(err), str(err)
            else:
                raise AssertionError("Missing pre-commit failure")
        finally:
            os.environ.pop("KEYPOOL_TEST_INTERRUPT_BEFORE_COMMIT", None)

        with pool.connect(db) as conn:
            interrupted = pool.load(conn)
            assert interrupted["next_i"] == 63 and interrupted["found"] == 0
            assert conn.execute(
                "SELECT count(*) FROM sqlite_master "
                "WHERE type='table' AND name='verified_hit'"
            ).fetchone()[0] == 0
        assert int((folder / "FOUND.private").read_text().strip(), 16) == KEY

        # Restart the same campaign. This replays the only uncommitted chunk,
        # tolerates the existing matching file and atomically stores the key.
        pool.run(db, worker, max_jobs=1, timeout=30, window=4)
        with pool.connect(db) as conn:
            final = pool.load(conn)
            assert final["next_i"] == 64 and final["found"] == 1
            record = conn.execute(
                "SELECT private_key_hex, job_index, verified_at_utc "
                "FROM verified_hit WHERE campaign_id=1"
            ).fetchone()
            assert record is not None
            key_hex, job_index, recorded = record
            assert key_hex == "0x" + format(KEY, "064x")
            assert job_index == 63 and recorded
            assert pool.verify_hit(key_hex, pool.FIXTURE_TARGET)
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        hit = folder / "FOUND.private"
        assert stat.S_IMODE(hit.stat().st_mode) == 0o600

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            pool.status(db)
        assert '"found": true' in output.getvalue()
        assert key_hex not in output.getvalue(), "Never leak key via status"

        # Online snapshot backs up the extra table automatically.
        backup = folder / "offline-copy.sqlite3"
        with sqlite3.connect(db) as source, sqlite3.connect(backup) as dest:
            source.backup(dest)

        # Simulate losing FOUND.private. A verified key remains recoverable
        # from BOTH the live SQLite DB and an off-device-style SQLite copy.
        hit.unlink()
        for source in (db, backup):
            with sqlite3.connect(source) as conn:
                k = conn.execute(
                    "SELECT private_key_hex FROM verified_hit WHERE campaign_id=1"
                ).fetchone()[0]
                assert pool.verify_hit(k, pool.FIXTURE_TARGET)
                assert int(k, 16) == KEY
                assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    print("PASS: untouched legacy schema until hit; no production DB access")
    print("PASS: injected crash leaves found+key uncommitted and retry succeeds")
    print("PASS: verified key stored with found flag, redacted status, valid backup")
    print("PASS: recover secret from either SQLite copy after file loss")


if __name__ == "__main__":
    main()
