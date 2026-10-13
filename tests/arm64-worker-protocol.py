#!/usr/bin/env python3
"""KISS worker contract: persistent process, strict disjoint slices, known hit."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "keyhunt-worker"
TARGET = "1HsMJxNiV7TLxmoF6uJNkydxPFDog4NQum"  # solved puzzle 20
SOLVED = 0xD2C55


def job(job_id, lo, hi):
    return json.dumps(
        {"id": job_id, "start": hex(lo), "end_exclusive": hex(hi)},
        separators=(",", ":"),
    )


def test():
    assert BIN.is_file(), "build with make arm64-worker first"
    with tempfile.TemporaryDirectory(prefix="keyhunt-worker-") as tmp:
        work = Path(tmp)
        target = work / "target.txt"
        target.write_text(TARGET + "\n", encoding="ascii")
        args = [
            str(BIN), "-m", "address", "-f", str(target),
            "-l", "compress", "-t", "4", "-n", "0x4000", "-q", "-s", "0",
        ]
        # Invalid jobs must not change the cursor, or launch computation.
        ranges = [(0x200000, 0x210000), (0x300000, 0x310000),
                  (0xD0000, 0xE0000)]
        requests = [
            job(1, 0, 0x1000),
            job(2, 0x200000, 0x200001),
            job(3, *ranges[0]),
            job(4, *ranges[1]),
            job(5, *ranges[2]),
        ]
        env = os.environ.copy()
        env["KEYHUNT_WORKER_TRACE"] = "1"
        try:
            done = subprocess.run(
                args, input="\n".join(requests) + "\n",
                text=True, cwd=work, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AssertionError(
                f"worker hung: stdout={(exc.stdout or b'')[-1500:]!r} "
                f"stderr={(exc.stderr or b'')[-2500:]!r}"
            ) from exc
        if done.returncode:
            raise AssertionError(
                f"worker exited {done.returncode}: {done.stderr[-2500:]}"
            )
        try:
            replies = [json.loads(l) for l in done.stdout.splitlines()]
        except ValueError as exc:
            raise AssertionError(f"non-JSON protocol output: {done.stdout}") from exc
        assert len(replies) == len(requests), replies
        assert [r["type"] for r in replies] == [
            "error", "error", "complete", "complete", "hit"
        ], replies
        assert [r.get("id") for r in replies[2:]] == [3, 4, 5], replies
        assert all(r["count"] == 0x10000 for r in replies[2:]), replies
        assert int(replies[-1]["key"], 16) == SOLVED, replies[-1]
        assert "Hit! Private Key:" not in done.stderr, "secret leaked to logs"
        assert "Private Key:" not in done.stderr, "secret leaked to logs"

        slices = [(int(a, 16), int(b)) for a, b in re.findall(
            r"WORKER_SLICE start=([0-9a-fA-F]+) count=(\d+)", done.stderr
        )]
        assert slices, "trace did not record any assigned slices"
        # Compare the union of actually assigned work to the exact jobs.
        actual = sorted((start, start + count) for start, count in slices)
        expected = sorted(ranges)
        cursor = None
        for start, end in actual:
            assert 0 < end - start <= 0x4000, (start, end)
            assert (end - start) % 1024 == 0, (start, end)
            if cursor is not None and start == cursor:
                cursor = end
            else:
                assert cursor is None or start > cursor, "slice overlap"
                cursor = end
        for lo, hi in expected:
            parts = sorted((a, b) for a, b in actual if lo <= a and b <= hi)
            assert parts, (lo, hi, actual)
            current = lo
            for a, b in parts:
                assert a == current, (hex(current), hex(a), hex(b))
                current = b
            assert current == hi, (hex(current), hex(hi))
        assert sum(b - a for a, b in actual) == sum(
            b - a for a, b in expected
        ), "missing or extra slices"
        print("PASS: persistent worker processed sequential jobs")
        print("PASS: invalid ranges rejected without scanning")
        print("PASS: four-core job slices exactly cover the assigned intervals")
        print("PASS: independently recovered known puzzle 20 key; no log leak")


if __name__ == "__main__":
    test()
