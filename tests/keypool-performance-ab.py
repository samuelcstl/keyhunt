#!/usr/bin/env python3
"""Pi 5 A/B/C: standalone NEON vs direct worker vs SQLite Keypool.

Diagnostic-only campaigns live in a separate private run directory.
Never reads, changes, or advances ~/.local/state/keypool/campaign.sqlite3.
"""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import select
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1-neon"
WORKER = ROOT / "keyhunt-worker"
TARGET_FILE = ROOT.parent / "runs/bench71/target.txt"
OUTPUT_ROOT = ROOT.parent / "runs/keypool-performance-ab"

spec = importlib.util.spec_from_file_location("keypoold", ROOT / "pool/keypoold.py")
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)
STAT = re.compile(r"Total\s+(\d+)\s+keys in\s+(\d+)\s+seconds:.*?(?:\((\d+)\s+keys/s\)|(\d+)\s+keys/s)")


def command_output(*args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=3)
        return p.stdout.strip() if p.returncode == 0 else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def sensors():
    return {
        "temp": command_output("vcgencmd", "measure_temp"),
        "clock": command_output("vcgencmd", "measure_clock", "arm"),
        "throttled": command_output("vcgencmd", "get_throttled"),
    }


def worker_args():
    return [str(WORKER), "-m", "address", "-f", str(TARGET_FILE),
            "-l", "compress", "-t", "4", "-n", "0x40000", "-q", "-s", "0"]


def clean_env():
    env = os.environ.copy()
    for key in ("KEYHUNT_WORKER_TRACE", "KEYHUNT_WORKER_COVERAGE",
                "KEYPOOL_TEST_INTERRUPT_BEFORE_COMMIT"):
        env.pop(key, None)
    return env


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def standalone(directory, seconds, _jobs):
    log = directory / "standalone.log"
    cmd = [str(BASE), "-m", "address", "-f", str(TARGET_FILE),
           "-b", "71", "-l", "compress", "-R", "-n", "0x100000",
           "-t", "4", "-q", "-s", "5"]
    with log.open("w") as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT,
                                env=clean_env(), cwd=directory)
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                if proc.poll() is not None:
                    raise RuntimeError(f"Standalone exited early; see {log}")
                time.sleep(max(0.0, min(1.0, end - time.monotonic())))
        finally:
            stop(proc)
    matches = STAT.findall(log.read_text(errors="replace").replace("\r", "\n"))
    if not matches:
        raise RuntimeError(f"No standalone throughput samples in {log}")
    last = matches[-1]
    total, sampled_seconds = int(last[0]), int(last[1])
    rate = int(last[2] or last[3])
    if total <= 0 or sampled_seconds < 5 or rate <= 0:
        raise RuntimeError(f"Invalid standalone throughput sample: {last}")
    return {"keys": total, "elapsed": sampled_seconds,
            "rate": rate / 1e6, "detail": "native 5s-counter average"}


def direct_worker(directory, _seconds, jobs):
    log = directory / "worker.log"
    seed = secrets.token_bytes(16)
    count = 0
    with log.open("w") as f:
        proc = subprocess.Popen(worker_args(), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=f,
                                text=True, bufsize=1, env=clean_env(), cwd=directory)
        start = time.perf_counter()
        try:
            for i in range(jobs):
                block = pool.permute(i, seed)
                lo = pool.LOWER + block * pool.CHUNK
                job = {"id": i, "start": hex(lo),
                       "end_exclusive": hex(lo + pool.CHUNK)}
                proc.stdin.write(json.dumps(job, separators=(",", ":")) + "\n")
                proc.stdin.flush()
                ready, _, _ = select.select([proc.stdout], [], [], 60)
                if not ready:
                    raise RuntimeError(f"Direct worker timed out on job {i}")
                line = proc.stdout.readline()
                if not line:
                    raise RuntimeError(f"Direct worker exited on job {i}")
                response = json.loads(line)
                if response.get("id") != i or response.get("count") != pool.CHUNK:
                    raise RuntimeError(f"Invalid completion for direct job {i}")
                if response.get("type") == "hit":
                    key = response.get("key", "")
                    if not isinstance(key, str) or not pool.verify_hit(key):
                        raise RuntimeError("Invalid reported direct-worker match")
                    (directory / "FOUND.private").write_text(key + "\n")
                    raise RuntimeError(f"Verified match preserved at {directory}/FOUND.private")
                if response.get("type") != "complete":
                    raise RuntimeError(f"Unexpected worker response on job {i}")
                count += pool.CHUNK
            elapsed = time.perf_counter() - start
            proc.stdin.close()
            rc = proc.wait(timeout=10)
            if rc:
                raise RuntimeError(f"Direct worker exit={rc}; see {log}")
        finally:
            stop(proc)
    return {"keys": count, "elapsed": elapsed,
            "rate": count / elapsed / 1e6, "detail": "acks / wall-clock"}


def sqlite_pool(directory, _seconds, jobs):
    db = directory / "campaign.sqlite3"
    pool.init(db, TARGET_FILE)
    log = directory / "keypool.log"
    cmd = [sys.executable, str(ROOT / "pool/keypoold.py"), "run",
           "--db", str(db), "--worker", str(WORKER),
           "--max-jobs", str(jobs), "--timeout", "60"]
    with log.open("w") as f:
        start = time.perf_counter()
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT,
                                env=clean_env(), cwd=directory)
        elapsed = time.perf_counter() - start
    if result.returncode:
        raise RuntimeError(f"SQLite Keypool failed; see {log}")
    with pool.connect(db) as conn:
        s = pool.load(conn)
    if s["found"]:
        raise RuntimeError(f"Verified match: preserve private result in {directory}")
    if s["next_i"] != jobs or s["inflight"] is not None or s["reissued"] != 0:
        raise RuntimeError(f"Unexpected Keypool checkpoint; see {db}")
    return {"keys": jobs * pool.CHUNK, "elapsed": elapsed,
            "rate": jobs * pool.CHUNK / elapsed / 1e6,
            "detail": "durable commits / wall-clock"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=256)
    ap.add_argument("--baseline-seconds", type=int, default=40)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--cooldown", type=int, default=5)
    args = ap.parse_args()
    if args.jobs < 8 or args.jobs >= (1 << 50):
        ap.error("--jobs must be >=8 and within Puzzle 71's domain")
    if args.baseline_seconds < 15 or args.repeats < 1 or args.cooldown < 0:
        ap.error("Minimum baseline duration 15s, repeats >=1, cooldown >=0")
    if not BASE.is_file() or not WORKER.is_file():
        ap.error("Build both: make arm64-neon-target arm64-worker")
    if not TARGET_FILE.is_file() or TARGET_FILE.read_text().strip() != pool.TARGET:
        ap.error("Missing or unexpected Puzzle 71 target file")
    os.umask(0o077)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = OUTPUT_ROOT / f"{tag}-{os.getpid()}"
    folder.mkdir(mode=0o700)
    rows = []
    variants = [
        ("standalone", standalone), ("direct-worker", direct_worker),
        ("sqlite-pool", sqlite_pool),
    ]
    print(f"Output: {folder}", flush=True)
    print("Standalone: legacy -R, native counter; other modes: completed jobs / wall time.")
    print("These are diagnostic runs; production Puzzle 71 cursor is NOT advanced.", flush=True)
    for rep in range(args.repeats):
        order = variants if rep % 2 == 0 else list(reversed(variants))
        for name, func in order:
            run_dir = folder / f"r{rep+1}-{name}"
            run_dir.mkdir(mode=0o700)
            before = sensors()
            print(f"Starting {name} repeat={rep+1} temp={before['temp']} "
                  f"clock={before['clock']} throttled={before['throttled']}", flush=True)
            data = func(run_dir, args.baseline_seconds, args.jobs)
            after = sensors()
            row = dict(repeat=rep+1, variant=name, **data,
                       temp_before=before["temp"], temp_after=after["temp"],
                       clock_before=before["clock"], clock_after=after["clock"],
                       throttled_before=before["throttled"],
                       throttled_after=after["throttled"])
            rows.append(row)
            with (folder / "results.tsv").open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)
            print(f"  {name}: {data['rate']:.3f} Mkeys/s "
                  f"({data['keys']:,} keys, {data['elapsed']:.1f}s) "
                  f"temp={after['temp']} clock={after['clock']} "
                  f"throttled={after['throttled']}", flush=True)
            if args.cooldown:
                time.sleep(args.cooldown)
    med = {name: statistics.median(x["rate"] for x in rows if x["variant"] == name)
           for name, _ in variants}
    print("\nMedian rates (Mkeys/s):")
    for name, rate in med.items():
        print(f"  {name:15s} {rate:.3f}")
    print(f"  direct vs standalone: {(med['direct-worker']/med['standalone']-1)*100:+.1f}%")
    print(f"  SQLite vs direct: {(med['sqlite-pool']/med['direct-worker']-1)*100:+.1f}%")
    print(f"  SQLite vs standalone: {(med['sqlite-pool']/med['standalone']-1)*100:+.1f}%")
    print(f"Raw logs, sensor snapshots, separate DBs and results: {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
