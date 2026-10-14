#!/usr/bin/env python3
"""KISS keypool scheduling/restart tests. No real puzzle work or hardware needed."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("keypoold", ROOT / "pool/keypoold.py")
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)


def main():
    seed = bytes.fromhex("00112233445566778899aabbccddeeff")
    for bits in (2, 4, 8, 12):
        actual = [pool.permute(i, seed, bits) for i in range(1 << bits)]
        assert sorted(actual) == list(range(1 << bits)), bits
    assert len({pool.permute(i, seed) for i in range(10000)}) == 10000
    assert all(0 <= pool.permute(i, seed) < (1 << 50)
               for i in (0, 1, 2, (1 << 50) - 1))
    print("PASS: deterministic, bijective Feistel chunk scheduling")

    with tempfile.TemporaryDirectory(prefix="keypool-controller-") as tmp:
        work = Path(tmp)
        db = work / "campaign.sqlite3"
        target = work / "target.txt"
        target.write_text(pool.TARGET + "\n", encoding="ascii")
        fake_log = work / "received.jsonl"
        worker = work / "fake-worker"
        worker.write_text(textwrap.dedent("""\
            #!/usr/bin/env python3
            import json, os, sys
            with open(os.environ["FAKE_WORKER_LOG"], "a") as log:
                for line in sys.stdin:
                    job = json.loads(line)
                    log.write(json.dumps(job) + "\\n")
                    log.flush()
                    if os.environ.get("FAKE_CRASH_FIRST") == "1":
                        sys.exit(3)
                    count = int(job["end_exclusive"], 16) - int(job["start"], 16)
                    print(json.dumps({"type":"complete", "id":job["id"],
                                      "count":count}), flush=True)
        """), encoding="ascii")
        worker.chmod(0o700)

        os.environ["FAKE_WORKER_LOG"] = str(fake_log)
        pool.init(db, target)
        with pool.connect(db) as c:
            state = pool.load(c)
            assert state["next_i"] == 0 and state["inflight"] is None
        pool.run(db, worker, max_jobs=2, timeout=10)
        with pool.connect(db) as c:
            state = pool.load(c)
            assert state["next_i"] == 2 and state["inflight"] is None

        os.environ["FAKE_CRASH_FIRST"] = "1"
        try:
            pool.run(db, worker, max_jobs=1, timeout=10)
        except RuntimeError as exc:
            assert "with uncommitted jobs" in str(exc), str(exc)
        else:
            raise AssertionError("Fake worker crash went unnoticed")
        finally:
            os.environ.pop("FAKE_CRASH_FIRST", None)
        with pool.connect(db) as c:
            state = pool.load(c)
            assert state["next_i"] == 2 and state["inflight"] == 2

        pool.run(db, worker, max_jobs=2, timeout=10)
        with pool.connect(db) as c:
            state = pool.load(c)
            assert state["next_i"] == 4 and state["inflight"] is None
            assert state["reissued"] == 1

        jobs = [json.loads(line) for line in fake_log.read_text().splitlines()]
        assert [j["id"] for j in jobs] == [0, 1, 2, 2, 3]
        assert jobs[2]["start"] == jobs[3]["start"]
        for j in jobs:
            assert int(j["end_exclusive"], 16) - int(j["start"], 16) == pool.CHUNK
        unique = {j["start"] for j in jobs}
        assert len(unique) == 4, unique
        print("PASS: cursor advances only after valid acknowledgements")
        print("PASS: crash reissues exactly the uncommitted job, never a committed one")
        print("PASS: SQLite holds one campaign row and compact, auditable progress")

        # New one-commit handoff: commit of job i also reserves i+1.
        # Kill precisely after the checkpoint but before i+1 is dispatched.
        # The restart must NOT repeat committed i nor skip reserved i+1.
        fixture_db = work / "preassigned-fixture.sqlite3"
        fixture_target = work / "fixture-target.txt"
        fixture_target.write_text(pool.FIXTURE_TARGET + chr(10), encoding="ascii")
        pool.init(fixture_db, fixture_target, fixture=True)
        os.environ["KEYPOOL_TEST_INTERRUPT_AFTER_COMMIT"] = "1"
        try:
            pool.run(fixture_db, worker, max_jobs=4, timeout=10)
        except RuntimeError as exc:
            assert "after checkpoint" in str(exc), str(exc)
        else:
            raise AssertionError("Missing postcommit/pre-dispatch injection")
        finally:
            os.environ.pop("KEYPOOL_TEST_INTERRUPT_AFTER_COMMIT", None)
        with pool.connect(fixture_db) as c:
            state = pool.load(c)
            assert state["next_i"] == 2 and state["inflight"] == 2
            assert state["reissued"] == 0
        pool.run(fixture_db, worker, max_jobs=2, timeout=10)
        with pool.connect(fixture_db) as c:
            state = pool.load(c)
            assert state["next_i"] == 4 and state["inflight"] is None
            assert state["reissued"] == 1
        fixture_jobs = [json.loads(line) for line in fake_log.read_text().splitlines()][5:]
        assert [j["id"] for j in fixture_jobs] == [0, 1, 2, 3, 2, 3], fixture_jobs
        print("PASS: pipelined restart never repeats committed jobs; only prefetched uncommitted jobs replay")


if __name__ == "__main__":
    main()
