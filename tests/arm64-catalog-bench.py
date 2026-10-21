#!/usr/bin/env python3
"""Bounded Pi5 screening of ALL versioned Keyhunt ARM64 catalog entries.

Full Keypool protocol throughput, field microbenchmarks and research pipelines
use distinct units / ranking groups. No SQLite is opened and no service starts.
"""
import argparse
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config/keyhunt-arm64-catalog.json"
BENCH = ROOT / "tests/keypool-performance-ab.py"
TARGET = ROOT.parent / "runs/bench71/target.txt"
TEST_SEED = bytes.fromhex("0f1e2d3c4b5a69788796a5b4c3d2e1f0")
COLUMNS = ("kind", "id", "family", "profile", "group", "metric",
           "variant", "rate", "unit", "repeat", "elapsed_s", "sha256",
           "clock_before", "clock_after", "temp_before", "temp_after",
           "throttle_before", "throttle_after")


def load_catalog():
    document = json.loads(CATALOG.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported catalog schema")
    entries = document["entries"]
    ids, paths = set(), set()
    if len(entries) != 23:
        raise ValueError(f"Expected exactly 23 catalog entries; got {len(entries)}")
    for item in entries:
        if item["id"] in ids or item["path"] in paths:
            raise ValueError("Duplicate id or executable path in catalog")
        ids.add(item["id"])
        paths.add(item["path"])
        if item["kind"] not in ("worker", "micro", "pipeline"):
            raise ValueError(f"Invalid kind: {item}")
        if item["profile"] not in ("on", "off", "none"):
            raise ValueError(f"Invalid instrumentation: {item}")
        path = Path(item["path"])
        if path.is_absolute() or ".." in path.parts or str(path).startswith("."):
            raise ValueError("Unsafe executable path in catalog")
        if item["kind"] == "worker" and not item["path"].startswith("keyhunt-worker"):
            raise ValueError("Worker not in Keypool binary namespace")
        if item["kind"] == "pipeline" and "hashed_Mkeys_s" != item["metric"]:
            raise ValueError("Pipeline cannot be reported in worker units")
    if document["production_default"] not in ids:
        raise ValueError("Missing unchanged production default")
    return entries


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for buf in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()


def command_text(*argv):
    try:
        p = subprocess.run(argv, text=True, capture_output=True, timeout=4)
        return p.stdout.strip() if p.returncode == 0 else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def sensors():
    return {
        "clock": command_text("vcgencmd", "measure_clock", "arm"),
        "temp": command_text("vcgencmd", "measure_temp"),
        "throttle": command_text("vcgencmd", "get_throttled"),
    }


def worker_child(filename, jobs, directory):
    """One observation in a process group, so parent can kill hard on budget."""
    spec = importlib.util.spec_from_file_location("keypool_perf", BENCH)
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    if TARGET.read_text(encoding="ascii").strip() != bench.pool.TARGET:
        raise RuntimeError("Wrong Puzzle71 target file")
    bench.WORKER = ROOT / filename
    bench.secrets.token_bytes = (
        lambda n: TEST_SEED if n == 16 else os.urandom(n))
    data = bench.direct_worker(directory, 0, jobs)
    print("CATALOG_WORKER_JSON " + json.dumps(data), flush=True)


def run_command(cmd, env, logfile, deadline, ceiling=90):
    remaining = deadline - time.monotonic()
    if remaining < 2:
        raise TimeoutError("Entire catalog wall-clock budget exhausted")
    limit = max(2, min(ceiling, remaining))
    with logfile.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=out,
                                stderr=subprocess.STDOUT, text=True,
                                start_new_session=True)
        try:
            rc = proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise TimeoutError(f"Observation exceeded {limit:.1f}s: {logfile}")
    if rc:
        raise RuntimeError(f"Observation failed, exit={rc}: {logfile}")
    return logfile.read_text(encoding="utf-8", errors="replace")


def observe_worker(item, idx, rep, folder, args, deadline):
    obs = folder / f"{idx:02d}-{item['id']}-r{rep}"
    obs.mkdir(mode=0o700)
    env = os.environ.copy()
    for key in ("KEYHUNT_WORKER_TRACE", "KEYHUNT_WORKER_COVERAGE",
                "KEYHUNT_R7_STAGE_PROFILE",
                "KEYPOOL_TEST_INTERRUPT_BEFORE_COMMIT",
                "KEYPOOL_TEST_INTERRUPT_AFTER_COMMIT"):
        env.pop(key, None)
    if item["profile"] == "on":
        env["KEYHUNT_R7_STAGE_PROFILE"] = "1"
    cmd = [sys.executable, str(Path(__file__).resolve()), "_worker",
           item["path"], str(args.jobs), str(obs)]
    before = sensors()
    started = time.monotonic()
    text = run_command(cmd, env, obs / "observation.log", deadline,
                       ceiling=args.observation_timeout)
    elapsed = time.monotonic() - started
    after = sensors()
    parsed = [x.split("CATALOG_WORKER_JSON ", 1)[1]
              for x in text.splitlines() if x.startswith("CATALOG_WORKER_JSON ")]
    if len(parsed) != 1:
        raise RuntimeError(f"Missing one worker outcome: {obs}")
    result = json.loads(parsed[0])
    if result["keys"] != args.jobs * (1 << 20):
        raise RuntimeError("Incorrect completed scalar count")
    stages = (obs / "worker.log").read_text(errors="replace")
    markers = stages.count("R7_STAGES worker=")
    if item["profile"] == "on" and markers < 4:
        raise RuntimeError("Requested stage profiling did not emit 4 worker rows")
    if item["profile"] != "on" and markers:
        raise RuntimeError("Unprofiled worker emitted R7 stage timing")
    return [make_row(item, "worker-complete", result["rate"], rep, elapsed,
                     before, after)]


def make_row(item, variant, rate, rep, elapsed, before, after):
    return {
        "kind": item["kind"], "id": item["id"], "family": item["family"],
        "profile": item["profile"],
        "group": item.get("comparison_group", item["kind"] + "_" + item["family"] + ("_" + item["profile"] if item["kind"] == "pipeline" else "")),
        "metric": item["metric"], "variant": variant,
        "rate": float(rate), "unit": item["unit"], "repeat": rep,
        "elapsed_s": round(elapsed, 5), "sha256": item["_sha"],
        "clock_before": before["clock"], "clock_after": after["clock"],
        "temp_before": before["temp"], "temp_after": after["temp"],
        "throttle_before": before["throttle"], "throttle_after": after["throttle"],
    }


def observe_lab(item, idx, rep, folder, args, deadline):
    command = [str(ROOT / item["path"])]
    command.extend(str(arg).replace("{seconds}", str(args.seconds))
                   for arg in item["args"])
    env = os.environ.copy()
    env.pop("KEYHUNT_R7_STAGE_PROFILE", None)
    before = sensors()
    started = time.monotonic()
    log = folder / f"{idx:02d}-{item['id']}-r{rep}.csv.log"
    output = run_command(command, env, log, deadline,
                         ceiling=args.observation_timeout)
    elapsed = time.monotonic() - started
    after = sensors()
    lines = output.splitlines()
    header_idx = next(
        (i for i, row in enumerate(lines) if row.startswith("repeat,") or
         row.startswith("width,") or row.startswith("producers,")),
        None)
    if header_idx is None:
        raise RuntimeError(f"Experiment lacks parseable CSV header: {log}")
    # Benchmarks write valid CSV to stdout and end with a checksum on
    # stderr. They share one evidence log, so checksum text is NOT a CSV row.
    header = lines[header_idx]
    expected_commas = header.count(",")
    records = [line for line in lines[header_idx + 1:]
               if line.count(",") == expected_commas]
    parsed = list(csv.DictReader(io.StringIO("\n".join([header, *records]))))
    if not parsed:
        raise RuntimeError(f"No complete CSV measurements in {log}")
    out = []
    for row in parsed:
        if item["metric"] not in row:
            raise RuntimeError(f"Missing {item['metric']} in {log}")
        if item["kind"] == "pipeline":
            if (int(row["produced_keys"]) != int(row["hashed_keys"]) or
                    int(row["hashed_keys"]) <= 0 or row["mode"] != "bench"):
                raise RuntimeError(f"Invalid indexed pipeline coverage: {log}")
        variation = row.get("variant", row.get("width", "profile-" + item["profile"]))
        out.append(make_row(item, str(variation), row[item["metric"]], rep,
                            elapsed, before, after))
    return out


def save_table(rows, path):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, COLUMNS, delimiter="\t")
        writer.writeheader()
        for item in rows:
            writer.writerow(item)


def summary(rows, entries, path):
    groups = {}
    for row in rows:
        key = (row["group"], row["id"], row["variant"])
        groups.setdefault(key, []).append(row["rate"])
    lines = [
        "Full catalog screening, units NOT interchangeable between groups.",
        "A ranking is valid only within the same group, metric and instrumentation.",
        "Default is two short observations: screening, NOT production qualification.",
        "",
        "Group\tVariant\tProfile\tMedian throughput\tObservations\tUnit",
    ]
    lookup = {item["id"]: item for item in entries}
    for (group, ident, variant), values in sorted(groups.items()):
        item = lookup[ident]
        lines.append(
            f"{group}\t{ident}/{variant}\t{item['profile']}\t"
            f"{statistics.median(values):.6f}\t{len(values)}\t{item['unit']}")
    # Quantify profiling cost *only* for matched algorithms/configurations.
    # This is not a Keypool-vs-pipeline ranking.
    profile_pairs = [
        ("r7-sched-on", "r7-sched-off"),
        ("r7-pair-on", "r7-pair-off"),
        ("r7-fold-on", "r7-fold-off"),
        ("r8-pipeline-on", "r8-pipeline-off"),
        ("r9-pipeline-on", "r9-pipeline-off"),
        ("r10-pipeline-on", "r10-pipeline-off"),
    ]
    lines.extend(["", "Instrumentation overhead (ON / OFF - 1), matched executable family:"])
    for on, off in profile_pairs:
        left = [r["rate"] for r in rows if r["id"] == on]
        right = [r["rate"] for r in rows if r["id"] == off]
        if not left or not right:
            continue
        if len(left) != len(right):
            raise RuntimeError(f"Unbalanced instrumented pair: {on} / {off}")
        penalty = 100 * (statistics.median(left) /
                         statistics.median(right) - 1)
        lines.append(f"{on} vs {off}: {penalty:+.3f}% throughput")
    result = "\n".join(lines) + "\n"
    path.write_text(result, encoding="utf-8")
    print(result, flush=True)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "_worker":
        if len(sys.argv) != 5:
            raise SystemExit("Internal worker invocation only")
        d = Path(sys.argv[4])
        worker_child(sys.argv[2], int(sys.argv[3]), d)
        return
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true",
                    help="Print all catalog entries, no build or benchmark")
    ap.add_argument("--selftest", action="store_true",
                    help="Validate catalog shape and print counts")
    ap.add_argument("--mode", choices=("all", "workers", "micro", "pipelines"),
                    default="all")
    ap.add_argument("--jobs", type=int, default=64,
                    help="2^20-key chunks per worker observation")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--seconds", type=float, default=2.0,
                    help="Approx seconds per microbenchmark configuration")
    ap.add_argument("--max-seconds", type=int, default=420)
    ap.add_argument("--observation-timeout", type=int, default=75)
    ap.add_argument("--run-dir", type=Path)
    args = ap.parse_args()
    entries = load_catalog()
    if args.list or args.selftest:
        for entry in entries if args.list else []:
            print(f"{entry['id']:18} {entry['kind']:9} {entry['profile']:4} "
                  f"{entry['path']}")
        if args.selftest:
            print("Catalog OK: 23 entries (14 Keypool workers, 3 micro, 6 pipelines)")
        return
    if args.jobs < 8 or args.repeats not in (1, 2, 3) or not 0.5 <= args.seconds <= 10:
        ap.error("jobs>=8, repeats 1..3, seconds 0.5..10")
    if args.max_seconds < 60 or args.observation_timeout < 10:
        ap.error("Timeout budget too small")
    if command_text("uname", "-m") != "aarch64":
        ap.error("Physical ARM64 Pi required")
    if not TARGET.is_file():
        ap.error(f"Puzzle71 public target file missing: {TARGET}")
    groups = {"all": {"worker", "micro", "pipeline"},
              "workers": {"worker"}, "micro": {"micro"},
              "pipelines": {"pipeline"}}
    selected = [x for x in entries if x["kind"] in groups[args.mode]]
    for item in selected:
        executable = ROOT / item["path"]
        if not executable.is_file() or not os.access(executable, os.X_OK):
            ap.error(f"Build first: make arm64-catalog-build ({executable})")
        item["_sha"] = sha256(executable)
    os.umask(0o077)
    folder = args.run_dir or ROOT.parent / "runs/arm64-catalog" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
        f"-{os.getpid()}")
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    provenance = {
        "commit": command_text("git", "rev-parse", "HEAD"),
        "machine": command_text("uname", "-a"),
        "compiler": command_text("g++", "--version").splitlines()[0],
        "target_file_sha256": sha256(TARGET),
        "test_seed": TEST_SEED.hex(), "mode": args.mode,
        "jobs": args.jobs, "repeats": args.repeats,
        "seconds": args.seconds, "max_seconds": args.max_seconds,
        "production_db_access": "NONE (direct worker and standalone labs only)",
        "inventory": [{"id": e["id"], "path": e["path"],
                       "sha256": e["_sha"], "profile": e["profile"]}
                      for e in selected],
    }
    (folder / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n")
    rows = []
    deadline = time.monotonic() + args.max_seconds
    # Reverse order on repeat 2/3. All worker variants see IDENTICAL seeded
    # Puzzle71 chunks. No SQLite is touched. Conditions are intentionally
    # approximate: screen finalists later with longer paired trials.
    try:
        for rep in range(1, args.repeats + 1):
            order = selected if rep % 2 else list(reversed(selected))
            for idx, item in enumerate(order):
                print(f"[{rep}/{args.repeats}] {item['id']}"
                      f" [{item['kind']}/{item['profile']}]",
                      flush=True)
                result = (observe_worker(item, idx, rep, folder, args, deadline)
                          if item["kind"] == "worker"
                          else observe_lab(item, idx, rep, folder, args, deadline))
                rows.extend(result)
                save_table(rows, folder / "results.tsv")
    finally:
        save_table(rows, folder / "results.tsv")
        if rows:
            summary(rows, selected, folder / "summary.txt")
    if len({(v["id"], v["repeat"]) for v in rows}) != len(selected) * args.repeats:
        raise RuntimeError("Incomplete catalog; do not rank")
    print("PASS: all selected catalog binaries benchmarked without SQLite", flush=True)


if __name__ == "__main__":
    main()
