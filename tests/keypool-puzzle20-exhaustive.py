#!/usr/bin/env python3
"""Full Puzzle #20 coverage and replay oracle through real Keypool -> NEON worker.

Intentional, publicly solved puzzle. Separate temporary DB; never opens,
initializes, advances, or changes the user's existing Puzzle #71 campaign.
"""
from collections import Counter
import importlib.util
import os
from pathlib import Path
import re
import stat
import tempfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("keypoold", ROOT / "pool/keypoold.py")
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)

KEY = 0xD2C55
GROUP = 1024
WORKER_SLICE = 2048
SCAN = re.compile(r"WORKER_SCANNED start=([0-9a-fA-F]+) count=(\d+)")
SLICE = re.compile(r"WORKER_SLICE start=([0-9a-fA-F]+) count=(\d+)")


def parse(logs, pattern):
    return [(int(start, 16), int(count))
            for log in logs for start, count in pattern.findall(log)]


def main():
    worker = ROOT / "keyhunt-worker"
    if not worker.is_file():
        raise SystemExit("Build first: make arm64-worker")
    lower, upper, chunk, size = (
        pool.FIXTURE_LOWER, pool.FIXTURE_UPPER,
        pool.FIXTURE_CHUNK, pool.FIXTURE_COUNT)
    seed = bytes.fromhex(pool.FIXTURE_SEED)
    assert size == 64 and upper-lower == 524288
    known_chunk = (KEY-lower)//chunk
    assert pool.permute(size-1, seed, pool.FIXTURE_BITS) == known_chunk
    order = [pool.permute(i, seed, pool.FIXTURE_BITS) for i in range(size)]
    assert len(set(order)) == size and order != list(range(size))
    assert all(order[i] != known_chunk for i in range(size-1))

    with tempfile.TemporaryDirectory(prefix="keypool-puzzle20-exhaustive-") as tmp:
        work = Path(tmp)
        db = work/"fixture.sqlite3"
        target = work/"target.txt"
        target.write_text(pool.FIXTURE_TARGET+"\n", encoding="ascii")
        assert db.resolve() != pool.DEFAULT_DB.resolve()
        pool.init(db, target, fixture=True)
        original_environment = {
            name: os.environ.get(name) for name in
            ("KEYHUNT_WORKER_TRACE", "KEYHUNT_WORKER_COVERAGE",
             "KEYPOOL_TEST_INTERRUPT_BEFORE_COMMIT")
        }
        logs = []
        try:
            os.environ["KEYHUNT_WORKER_TRACE"] = "1"
            os.environ["KEYHUNT_WORKER_COVERAGE"] = "1"
            os.environ.pop("KEYPOOL_TEST_INTERRUPT_BEFORE_COMMIT", None)

            # First 23 distinct chunks, then a deliberate crash after the
            # 24th was fully scanned but BEFORE the SQLite commit.
            pool.run(db, worker, max_jobs=23, timeout=60)
            logs.append((work/"worker.log").read_text(encoding="utf-8"))
            with pool.connect(db) as conn:
                state=pool.load(conn)
                assert state["next_i"] == 23 and state["inflight"] is None

            os.environ["KEYPOOL_TEST_INTERRUPT_BEFORE_COMMIT"]="23"
            try:
                pool.run(db, worker, max_jobs=1, timeout=60)
            except RuntimeError as exc:
                assert "Injected fixture crash" in str(exc), exc
            else:
                raise AssertionError("Expected precommit fault did not occur")
            logs.append((work/"worker.log").read_text(encoding="utf-8"))
            with pool.connect(db) as conn:
                state=pool.load(conn)
                assert state["next_i"] == 23 and state["inflight"] == 23
            os.environ.pop("KEYPOOL_TEST_INTERRUPT_BEFORE_COMMIT", None)

            # Exactly that uncommitted chunk must be replayed. Then finish
            # every remaining chunk. The real known key is in ordinal 63.
            pool.run(db, worker, max_jobs=40, timeout=60)
            logs.append((work/"worker.log").read_text(encoding="utf-8"))
            with pool.connect(db) as conn:
                state=pool.load(conn)
                assert state["next_i"] == 63 and state["inflight"] is None
                assert state["reissued"] == 1 and state["found"] == 0

            pool.run(db, worker, max_jobs=1, timeout=60)
            logs.append((work/"worker.log").read_text(encoding="utf-8"))
            with pool.connect(db) as conn:
                state=pool.load(conn)
                assert state["next_i"] == size
                assert state["inflight"] is None
                assert state["reissued"] == 1
                assert state["found"] == 1
        finally:
            for name, previous in original_environment.items():
                if previous is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = previous

        # Oracle #1: each chunk's four disjoint worker slices must appear.
        slices = parse(logs, SLICE)
        expected_slices = [
            (lower + block*chunk + k*WORKER_SLICE, WORKER_SLICE)
            for block in order for k in range(chunk//WORKER_SLICE)
        ]
        replay_block=order[23]
        replay_slices=[
            (lower + replay_block*chunk + k*WORKER_SLICE, WORKER_SLICE)
            for k in range(chunk//WORKER_SLICE)
        ]
        assert Counter(slices) == Counter(expected_slices+replay_slices), (
            "worker sliced a gap, overlap, or out-of-bounds interval")

        # Oracle #2: post-HASH160 instrumentation, not just allocated slices.
        scanned = parse(logs, SCAN)
        expected_groups = [(key, GROUP) for key in range(lower, upper, GROUP)]
        duplicate_groups = [
            (lower + replay_block*chunk + k*GROUP, GROUP)
            for k in range(chunk//GROUP)
        ]
        assert Counter(scanned) == Counter(expected_groups+duplicate_groups), (
            "post-HASH160 group trace shows a missing or unexpectedly "
            "duplicated group")
        assert len(scanned) == len(expected_groups)+len(duplicate_groups)
        assert all(GROUP == count for _, count in scanned)
        assert sum(c for _, c in expected_groups) == upper-lower
        assert sum(c for _, c in duplicate_groups) == chunk

        # Oracle #3: order of successive jobs observed in worker traces.
        job_ord={block:i for i,block in enumerate(order)}
        observed_order=[]
        for start, count in slices:
            block=(start-lower)//chunk
            job_i=job_ord[block]
            if not observed_order or observed_order[-1] != job_i:
                observed_order.append(job_i)
        assert observed_order == list(range(24))+list(range(23,64)), observed_order

        # Hit must be recovered only when last chunk is completed.
        found=work/"FOUND.private"
        assert found.is_file() and int(found.read_text().strip(),16) == KEY
        assert stat.S_IMODE(found.stat().st_mode) == 0o600
        assert all("Private Key:" not in log for log in logs)
        print("PASS: 64 randomized, disjoint Puzzle 20 chunks, verified actual dispatch order")
        print("PASS: 512/512 SHA256+RIPEMD160 groups account for all 524288 distinct keys")
        print("PASS: only eight 1024-key groups repeated after injected precommit crash")
        print("PASS: durable cursor 64, 1 recorded replay, and correct final known private key")
        print("PASS: production Puzzle 71 SQLite campaign was never touched")


if __name__ == "__main__":
    main()
