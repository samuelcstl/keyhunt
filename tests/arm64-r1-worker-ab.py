#!/usr/bin/env python3
"""Paired Pi-only throughput of baseline and R1 persistent workers.

Runs identical, preselected Puzzle #71 test chunks through the *real* four-job
worker protocol. Each observation uses its own scratch directory. The existing
Keypool campaign DB, configuration, worker binary and cursor are untouched.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT.parent / "runs" / "arm64-r1-worker-ab"
BENCH_FILE = ROOT / "tests" / "keypool-performance-ab.py"

def load_bench():
    spec = importlib.util.spec_from_file_location("r1_base_bench", BENCH_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def cmd(*args):
    try:
        r = subprocess.run(args, text=True, capture_output=True, timeout=5)
        return (r.stdout or r.stderr).strip() if r.returncode == 0 else f"failed ({r.returncode})"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for buf in iter(lambda: source.read(1024*1024), b""):
            h.update(buf)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=256)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--control", default="keyhunt-worker")
    parser.add_argument("--candidate", default="keyhunt-worker-r1")
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    if args.jobs < 8 or args.repeats < 2:
        parser.error("Use at least 8 jobs and 2 repeats")
    for name in (args.control, args.candidate):
        if name.startswith("/") or "/" in name or not (ROOT/name).is_file():
            parser.error(f"Expected a built worker in the repo root: {name}")

    bench = load_bench()
    if not bench.TARGET_FILE.is_file():
        parser.error(f"Missing validated Puzzle #71 target: {bench.TARGET_FILE}")
    if not hasattr(bench, "direct_worker"):
        parser.error("Missing original direct-worker benchmark adapter")

    folder = args.run_dir or OUTPUT_ROOT / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}")
    folder.mkdir(parents=True, exist_ok=False)
    os.chmod(folder, 0o700)
    controls = {
        "branch": cmd("git", "-C", str(ROOT), "branch", "--show-current"),
        "commit": cmd("git", "-C", str(ROOT), "rev-parse", "HEAD"),
        "compiler": cmd("g++", "--version").splitlines()[:1],
        "jobs_per_observation": args.jobs,
        "repeats": args.repeats,
        "input": str(bench.TARGET_FILE),
        "binaries": {n: digest(ROOT/n) for n in (args.control, args.candidate)},
        "mode": "full 4-thread worker JSON protocol, four prefetch jobs",
        "units": "fully completed candidate scalars / wall-clock (not hash ops)",
    }
    (folder/"provenance.json").write_text(json.dumps(controls, indent=2) + "\n")
    out = folder/"results.tsv"
    rows = []
    # The public benchmark's direct_worker() normally picks a random Feistel
    # seed per treatment. Fix a synthetic seed so both workers scan identical
    # chunk ordinals. It is NOT the existing live campaign seed.
    bench.secrets.token_bytes = lambda n: bytes.fromhex("0f1e2d3c4b5a69788796a5b4c3d2e1f0") if n == 16 else os.urandom(n)
    for rep in range(1, args.repeats+1):
        names = [args.control, args.candidate]
        if rep % 2 == 0:
            names.reverse()
        for name in names:
            work = folder/f"r{rep}-{name}"
            work.mkdir(mode=0o700)
            bench.WORKER = ROOT/name
            before = bench.sensors()
            outcome = bench.direct_worker(work, 0, args.jobs)
            after = bench.sensors()
            row = {
                "rep":rep, "worker":name,
                "keys":outcome["keys"], "elapsed_s":outcome["elapsed"],
                "mkeys_s":outcome["rate"],
                "clock_before":before["clock"],"clock_after":after["clock"],
                "temp_before":before["temp"],"temp_after":after["temp"],
                "throttle_before":before["throttled"],"throttle_after":after["throttled"],
            }
            rows.append(row)
            with out.open("w", newline="") as stream:
                writer = csv.DictWriter(stream,fieldnames=list(row),delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)
            print(f"r{rep} {name}: {outcome['rate']:.5f} Mkeys/s; "
                  f"{outcome['keys']:,} completed; {outcome['elapsed']:.2f}s; "
                  f"clock={after['clock']} temp={after['temp']} throttled={after['throttled']}",flush=True)
    paired = []
    for rep in range(1,args.repeats+1):
        control = next(r for r in rows if r["rep"]==rep and r["worker"]==args.control)
        candidate = next(r for r in rows if r["rep"]==rep and r["worker"]==args.candidate)
        paired.append(candidate["mkeys_s"]/control["mkeys_s"]-1)
    median = statistics.median(paired)
    summary = {"paired_deltas_percent": [100*d for d in paired],
               "paired_median_percent": 100*median,
               "wins":sum(d>0 for d in paired),
               "runs":args.repeats,
               "quality": "UNQUALIFIED: review thermals, clocks and interference manually"}
    (folder/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(f"R1 vs control: paired median {100*median:+.3f}%, "
          f"{summary['wins']}/{args.repeats} positive; evidence {folder}")
    print("Qualification remains manual: matching clocks, throttling, CPU occupancy and instruction-level PMU required.")

if __name__ == "__main__":
    main()
