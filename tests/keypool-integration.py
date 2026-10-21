#!/usr/bin/env python3
"""Integration: real NEON worker controlled by SQLite keypool, no daemon activation."""
import importlib.util
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("keypoold", ROOT / "pool/keypoold.py")
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)


def main():
    worker = ROOT / os.environ.get("KEYHUNT_WORKER_BIN", "keyhunt-worker")
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
        # Eight in one session exercises a full four-job in-flight window.
        pool.run(db, worker, max_jobs=8, timeout=90, window=4)
        with pool.connect(db) as conn:
            state = pool.load(conn)
            assert state["next_i"] == 12 and state["inflight"] is None, state
            assert state["reissued"] == 0 and state["found"] == 0, state

        # Exercise the actual direct-worker performance harness with the same
        # pipelined JSON reader (no standalone speed assumptions in CI).
        spec_bench = importlib.util.spec_from_file_location(
            "keypool_bench", ROOT / "tests/keypool-performance-ab.py")
        bench = importlib.util.module_from_spec(spec_bench)
        spec_bench.loader.exec_module(bench)
        bench.TARGET_FILE = target
        direct_dir = root / "direct-benchmark"
        direct_dir.mkdir()
        direct = bench.direct_worker(direct_dir, 0, 6)
        assert direct["keys"] == 6 * pool.CHUNK and direct["rate"] > 0, direct

        assert not (root / "FOUND.private").exists()
        log = (root / "worker.log").read_text(encoding="utf-8")
        assert "Private Key:" not in log, "secret leaked in worker stderr"
        print("PASS: keypoold dispatched four jobs to persistent NEON Keyhunt")
        print("PASS: two controller sessions advanced one persistent SQLite cursor")
        print("PASS: real-worker stdout JSON acknowledgement accepted only after full job")
        print("PASS: four-job prefetch and benchmark direct-worker pipeline verified with real ARM64 cryptography")


if __name__ == "__main__":
    main()
