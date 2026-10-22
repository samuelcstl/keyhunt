#!/usr/bin/env python3
"""SIGTERM regression: controller drains pending jobs while child stays alive.

Fixture uses only temporary SQLite and a deliberately slow mock worker.
systemd KillMode=mixed is verified separately by template validation.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pool"))
import keypoold as pool


def main():
    with tempfile.TemporaryDirectory(prefix="keypool-sigterm-fixture-") as temp:
        root = Path(temp)
        db = root / "campaign.sqlite3"
        target = root / "target.txt"
        worker = root / "fake-worker"
        received = root / "received.jsonl"
        target.write_text(pool.TARGET + "\n", encoding="ascii")
        pool.init(db, target)
        worker.write_text(textwrap.dedent("""\
            #!/usr/bin/env python3
            import json, os, sys, time
            for line in sys.stdin:
                job = json.loads(line)
                with open(os.environ["KEYPOOL_GRACEFUL_TEST_LOG"], "a") as out:
                    out.write(json.dumps(job) + "\\n")
                    out.flush()
                time.sleep(0.2)
                count = int(job["end_exclusive"], 16) - int(job["start"], 16)
                print(json.dumps({"type":"complete", "id":job["id"],
                                  "count":count}), flush=True)
        """), encoding="ascii")
        worker.chmod(0o700)
        env = os.environ.copy()
        env["KEYPOOL_GRACEFUL_TEST_LOG"] = str(received)
        command = [sys.executable, str(ROOT / "pool/keypoold.py"), "run",
                   "--db", str(db), "--worker", str(worker),
                   "--timeout", "10", "--window", "4"]
        proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env, text=True)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise AssertionError("Controller terminated before signal")
                if received.is_file() and received.stat().st_size:
                    break
                time.sleep(0.02)
            else:
                raise AssertionError("Mock worker never received a job")
            # The same signal topology as KillMode=mixed: main gets SIGTERM,
            # worker is not signaled until it finishes its own queued jobs.
            proc.send_signal(signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=15)
            assert proc.returncode == 0, (stdout, stderr)
            with pool.connect(db) as conn:
                state = pool.load(conn)
            jobs = [json.loads(line) for line in received.read_text().splitlines()]
            assert state["next_i"] == len(jobs), (state, jobs)
            assert 1 <= state["next_i"] <= 4, state
            assert state["inflight"] is None, state
            assert state["reissued"] == 0, state
            assert "Worker ended with uncommitted jobs" not in stderr
            print("PASS: SIGTERM parent-only drains outstanding worker jobs")
            # A clean next run must continue with the original cursor.
            old_i = state["next_i"]
            pool.run(db, worker, max_jobs=2, timeout=10)
            with pool.connect(db) as conn:
                resumed = pool.load(conn)
            assert resumed["next_i"] == old_i + 2, resumed
            assert resumed["inflight"] is None, resumed
            assert resumed["reissued"] == 0, resumed
            print("PASS: stopped campaign resumes without replay")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=5)


if __name__ == "__main__":
    main()
