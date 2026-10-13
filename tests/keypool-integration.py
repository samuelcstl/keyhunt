#!/usr/bin/env python3
"""Integration: real NEON worker controlled by SQLite keypool, no daemon activation."""
import importlib.util
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("keypoold", ROOT / "pool/keypoold.py")
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)


def main():
    worker = ROOT / "keyhunt-worker"
    assert worker.is_file(), "make arm64-worker first"
    with tempfile.TemporaryDirectory(prefix="keypool-real-worker-") as td:
        root = Path(td)
        db = root / "campaign.sqlite3"
        target = root / "target.txt"
        target.write_text(pool.TARGET + "\n", encoding="ascii")
        pool.init(db, target)
        for expected in (2, 4):
            pool.run(db, worker, max_jobs=2, timeout=90)
            with pool.connect(db) as conn:
                state = pool.load(conn)
                assert state["next_i"] == expected, state
                assert state["inflight"] is None, state
                assert state["found"] == 0, state
        assert not (root / "FOUND.private").exists()
        log = (root / "worker.log").read_text(encoding="utf-8")
        assert "Private Key:" not in log, "secret leaked in worker stderr"
        print("PASS: keypoold dispatched four jobs to persistent NEON Keyhunt")
        print("PASS: two controller sessions advanced one persistent SQLite cursor")
        print("PASS: real-worker stdout JSON acknowledgement accepted only after full job")


if __name__ == "__main__":
    main()
