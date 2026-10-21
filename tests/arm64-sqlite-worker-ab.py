#!/usr/bin/env python3
"""Paired production-controller test on disposable Puzzle71 SQLite campaigns.

Each run uses a new PRIVATE SQLite DB, identical Feistel seed, and matching jobs.
NEVER loads the default production database. Use with a CPU-quota systemd scope.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "pool/keypoold.py"
spec = importlib.util.spec_from_file_location("keypoold_qualification", SOURCE)
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)
FIXED_SEED = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"  # test-only
OUTPUT_ROOT = ROOT.parent / "runs/arm64-r7-sqlite-ab"


def sensors():
    result = {}
    for name, arguments in {
        "temp": ("measure_temp",),
        "clock": ("measure_clock", "arm"),
        "throttled": ("get_throttled",),
    }.items():
        try:
            p = subprocess.run(["vcgencmd", *arguments], text=True,
                               capture_output=True, timeout=4, check=False)
            result[name] = p.stdout.strip() if p.returncode == 0 else "unavailable"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result[name] = "unavailable"
    return result


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def measure(worker, folder, jobs, timeout):
    folder.mkdir(mode=0o700)
    db = folder / "campaign.sqlite3"
    if db.resolve() == pool.DEFAULT_DB.resolve():
        raise RuntimeError("Refusing production database")
    target_file = folder / "target.txt"
    target_file.write_text(pool.TARGET + "\n", encoding="ascii")
    pool.init(db, target_file)
    with pool.connect(db) as conn:
        conn.execute("UPDATE campaign SET seed=? WHERE id=1", (FIXED_SEED,))
        conn.commit()
    env = os.environ.copy()
    for k in ("KEYHUNT_WORKER_TRACE", "KEYHUNT_WORKER_COVERAGE",
              "KEYHUNT_R7_STAGE_PROFILE", "KEYPOOL_TEST_INTERRUPT_BEFORE_COMMIT",
              "KEYPOOL_TEST_INTERRUPT_AFTER_COMMIT"):
        env.pop(k, None)
    command = [sys.executable, str(SOURCE), "run", "--db", str(db),
               "--worker", str(worker), "--max-jobs", str(jobs),
               "--timeout", str(timeout), "--window", "4"]
    log = folder / "controller.log"
    with log.open("w", encoding="utf-8") as out:
        start = time.perf_counter()
        proc = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT,
                              cwd=folder, env=env, check=False)
        elapsed = time.perf_counter() - start
    if proc.returncode:
        raise RuntimeError(f"Controller failed for {worker.name}: {log}")
    with pool.connect(db) as conn:
        state = pool.load(conn)
    if state["found"]:
        raise RuntimeError("VERIFIED MATCH; keep this entire run private")
    if (state["next_i"] != jobs or state["inflight"] is not None or
            state["reissued"] != 0 or state["seed"] != FIXED_SEED):
        raise RuntimeError(f"Incorrect SQLite checkpoint for {worker.name}")
    return {"keys": jobs * pool.CHUNK, "elapsed_s": elapsed,
            "mkeys_s": jobs * pool.CHUNK / elapsed / 1_000_000}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--control", default="keyhunt-worker-r3-ecc-sched")
    ap.add_argument("--candidate", default="keyhunt-worker-r7-ecc-fold-unprofiled")
    ap.add_argument("--jobs", type=int, default=128)
    ap.add_argument("--repeats", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--run-dir", type=Path)
    args = ap.parse_args()
    if not 8 <= args.jobs < pool.COUNT or args.repeats < 2 or args.timeout < 10:
        ap.error("Need >=8 jobs, >=2 repeats, per-job timeout >=10s")
    workers = {}
    for label, filename in (("control", args.control), ("candidate", args.candidate)):
        if Path(filename).name != filename or filename.startswith("."):
            ap.error("Worker names must be simple filenames in the repo")
        worker = ROOT / filename
        if not worker.is_file() or not os.access(worker, os.X_OK):
            ap.error(f"Missing executable worker: {worker}")
        workers[label] = worker
    os.umask(0o077)
    folder = args.run_dir or OUTPUT_ROOT / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}")
    if folder.resolve() in (pool.DEFAULT_DB.resolve(), pool.DEFAULT_DB.parent.resolve()):
        ap.error("Refusing production state path")
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                         text=True, capture_output=True, check=True).stdout.strip()
    (folder / "provenance.json").write_text(json.dumps({
        "source_commit": sha, "test_seed": FIXED_SEED,
        "jobs": args.jobs, "repeats": args.repeats,
        "mode": "durably committed Keypool SQLite chunks",
        "default_campaign_opened": False,
        "workers": {name: {"filename": path.name, "sha256": digest(path)}
                    for name, path in workers.items()},
    }, indent=2) + "\n")
    rows = []
    for rep in range(1, args.repeats + 1):
        order = ("control", "candidate") if rep % 2 else ("candidate", "control")
        for name in order:
            before = sensors()
            data = measure(workers[name], folder / f"r{rep}-{name}", args.jobs,
                           args.timeout)
            after = sensors()
            row = {"repeat": rep, "worker": name, **data,
                   "clock_before": before["clock"], "clock_after": after["clock"],
                   "temp_before": before["temp"], "temp_after": after["temp"],
                   "throttle_before": before["throttled"],
                   "throttle_after": after["throttled"]}
            rows.append(row)
            with (folder / "results.tsv").open("w", newline="") as out:
                writer = csv.DictWriter(out, list(row), delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)
            print(f"r{rep} {name}: {data['mkeys_s']:.5f} Mkeys/s, "
                  f"{data['keys']:,} committed, {data['elapsed_s']:.2f}s",
                  flush=True)
    deltas = []
    for rep in range(1, args.repeats + 1):
        ref = next(x for x in rows if x["repeat"] == rep and x["worker"] == "control")
        trial = next(x for x in rows if x["repeat"] == rep and x["worker"] == "candidate")
        deltas.append(100 * (trial["mkeys_s"] / ref["mkeys_s"] - 1))
    summary = {"paired_deltas_percent": deltas,
               "paired_median_percent": statistics.median(deltas),
               "wins": sum(d > 0 for d in deltas), "runs": args.repeats,
               "qualification": "Review clocks, thermal stability, load and effect size"}
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Median R7 vs R3: {summary['paired_median_percent']:+.3f}% "
          f"({summary['wins']}/{args.repeats} wins). Evidence: {folder}")


if __name__ == "__main__":
    main()
