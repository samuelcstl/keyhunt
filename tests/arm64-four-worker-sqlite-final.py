#!/usr/bin/env python3
"""Balanced four-worker Keypool round robin on disposable Puzzle71 SQLite.

Only for manually-triggered Pi5 qualification under CPUQuota=150%.
Never reads/opens or updates the real Keypool campaign.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
POOL_SOURCE = ROOT / "pool" / "keypoold.py"
CATALOG = ROOT / "config" / "keyhunt-arm64-catalog.json"
spec = importlib.util.spec_from_file_location("keypool_four_way", POOL_SOURCE)
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)

SEED = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"  # test ONLY
IDS = ("r3-sched", "r7-pair-off", "r7-fold-off", "r2-sri")
# Four-period balanced Latin square: every engine occupies every test slot once.
ORDER = (
    ("r3-sched", "r7-pair-off", "r7-fold-off", "r2-sri"),
    ("r2-sri", "r7-fold-off", "r7-pair-off", "r3-sched"),
    ("r7-pair-off", "r2-sri", "r3-sched", "r7-fold-off"),
    ("r7-fold-off", "r3-sched", "r2-sri", "r7-pair-off"),
)
FIELDS = ["round", "slot", "worker", "phase", "keys", "elapsed_s", "mkeys_s",
          "clock_before", "clock_after", "temp_before", "temp_after",
          "throttle_before", "throttle_after", "cpu_quota"]


def validated_catalog():
    doc = json.loads(CATALOG.read_text(encoding="utf-8"))
    entries = {e["id"]: e for e in doc["entries"]}
    if set(IDS) - set(entries):
        raise ValueError("Missing finalist in repository catalog")
    selected = {}
    for ident in IDS:
        item = entries[ident]
        if item["kind"] != "worker" or item["profile"] not in ("none", "off"):
            raise ValueError("A finalist is not an unprofiled Keypool worker")
        name = Path(item["path"])
        if name.is_absolute() or name.name != item["path"]:
            raise ValueError("Worker must be in repository root")
        path = (ROOT / name).resolve()
        if path.parent != ROOT.resolve():
            raise ValueError("Unsafe worker path")
        selected[ident] = path
    return selected


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_order():
    if len(ORDER) != 4:
        raise AssertionError("Expected four Latin-square rounds")
    for row in ORDER:
        if set(row) != set(IDS):
            raise AssertionError("Wrong finalists or duplicates")
    for pos in range(4):
        if set(row[pos] for row in ORDER) != set(IDS):
            raise AssertionError("Not position-balanced")


def cpu_quota(ci_smoke=False):
    if ci_smoke and os.getenv("GITHUB_ACTIONS") == "true":
        return "CI_ONLY_unlimited"
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[:2] == ["0", ""]:
            cgfile = Path("/sys/fs/cgroup") / parts[2].lstrip("/") / "cpu.max"
            if not cgfile.is_file():
                raise RuntimeError("Missing cgroup v2 cpu.max; refuse unbounded run")
            quota, period = cgfile.read_text().split()
            if quota == "max":
                raise RuntimeError("CPU quota absent; run through systemd-run --user --scope -p CPUQuota=150%")
            q, p = int(quota), int(period)
            if not (1.49 <= q / p <= 1.51):
                raise RuntimeError(f"Expected CPUQuota=150%, found {q}/{p}")
            return f"{q}/{p}"
    raise RuntimeError("No unified cgroup v2 entry; refuse run")


def cmd(*argv):
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        if out.returncode:
            return "unavailable"
        return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def sensors():
    return {
        "clock": cmd("vcgencmd", "measure_clock", "arm"),
        "temp": cmd("vcgencmd", "measure_temp"),
        "throttle": cmd("vcgencmd", "get_throttled"),
    }


def production_db_metadata():
    path = pool.DEFAULT_DB
    # STAT ONLY, never sqlite3.connect() or load() the existing database.
    try:
        st = path.stat()
        return {"path": str(path), "size": st.st_size,
                "mtime_ns": st.st_mtime_ns}
    except FileNotFoundError:
        return {"path": str(path), "present": False}


def stop_process(proc):
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def observation(worker, directory, jobs, run_deadline, per_timeout):
    if directory.exists():
        raise RuntimeError(f"Refusing existing observation directory: {directory}")
    directory.mkdir(mode=0o700, parents=True)
    if directory.resolve() == pool.DEFAULT_DB.parent.resolve():
        raise RuntimeError("Refusing real campaign location")
    target_file = directory / "target.txt"
    target_file.write_text(pool.TARGET + "\n", encoding="ascii")
    db = directory / "campaign.sqlite3"
    if db.resolve() == pool.DEFAULT_DB.resolve():
        raise RuntimeError("Refusing production SQLite DB")
    pool.init(db, target_file)
    with pool.connect(db) as con:
        con.execute("UPDATE campaign SET seed=? WHERE id=1", (SEED,))
        con.commit()
    env = os.environ.copy()
    for name in ("KEYHUNT_WORKER_TRACE", "KEYHUNT_WORKER_COVERAGE",
                 "KEYHUNT_R7_STAGE_PROFILE",
                 "KEYPOOL_TEST_INTERRUPT_BEFORE_COMMIT",
                 "KEYPOOL_TEST_INTERRUPT_AFTER_COMMIT"):
        env.pop(name, None)
    args = (sys.executable, str(POOL_SOURCE), "run", "--db", str(db),
            "--worker", str(worker), "--max-jobs", str(jobs),
            "--timeout", "240", "--window", "4")
    before = sensors()
    begin = time.monotonic()
    left = run_deadline - begin
    if left < 15:
        raise TimeoutError("Global time budget exhausted")
    with (directory / "controller.log").open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(args, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = proc.wait(timeout=min(left, per_timeout))
        except subprocess.TimeoutExpired:
            stop_process(proc)
            raise TimeoutError(f"Controller exceeded budget; see {directory / 'controller.log'}")
        finally:
            stop_process(proc)
    elapsed = time.monotonic() - begin
    after = sensors()
    if (directory / "FOUND.private").exists():
        (directory.parent / "FOUND.private").touch(mode=0o600, exist_ok=True)
        raise RuntimeError("VERIFIED Puzzle71 hit: keep all evidence PRIVATE, do not upload")
    if rc:
        raise RuntimeError(f"Controller exit {rc}; see {directory / 'controller.log'}")
    with pool.connect(db) as con:
        integrity = con.execute("PRAGMA quick_check").fetchone()[0]
        state = pool.load(con)
    if integrity != "ok":
        raise RuntimeError("Scratch SQLite quick_check failed")
    if (state["next_i"] != jobs or state["inflight"] is not None or
            state["reissued"] != 0 or state["found"] != 0 or
            state["seed"] != SEED or state["version"] != pool.ALGO):
        raise RuntimeError(f"Scratch SQLite checkpoint invariant failed: {directory}")
    return {
        "keys": jobs * pool.CHUNK, "elapsed_s": round(elapsed, 6),
        "mkeys_s": round(jobs * pool.CHUNK / elapsed / 1e6, 7),
        "clock_before": before["clock"], "clock_after": after["clock"],
        "temp_before": before["temp"], "temp_after": after["temp"],
        "throttle_before": before["throttle"], "throttle_after": after["throttle"],
    }


def write_table(rows, path):
    with path.open("w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=FIELDS, delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def make_summary(rows, rounds, output):
    if len([r for r in rows if r["phase"] == "measured"]) != rounds * len(IDS):
        raise RuntimeError("Missing measurements; no final winner can be declared")
    groups = {v: {} for v in IDS}
    for row in rows:
        if row["phase"] == "measured":
            groups[row["worker"]][row["round"]] = row["mkeys_s"]
    if any(len(v) != rounds for v in groups.values()):
        raise RuntimeError("Unequal round coverage")
    lines = [
        "Full Keypool controller + disposable SQLite at verified CPUQuota=150%.",
        "Four position-balanced rounds; 96 x 2^20 exact candidates per observation by default.",
        "MATCHED ROUNDS use the same Feistel seed and dispatched chunks.",
        "All rates include controller startup and SQLite checkpoint cost.",
        "This remains a test; other Linux services can introduce measurement noise.",
        "",
        "Variant\tMean Mkeys/s\tMedian Mkeys/s\tvs R3 matched median %\tWins vs R3",
    ]
    ref = groups["r3-sched"]
    result = {"reference": "r3-sched", "rounds": rounds, "engines": {}}
    for name in IDS:
        values = [groups[name][i] for i in range(1, rounds + 1)]
        deltas = [100 * (groups[name][i] / ref[i] - 1) for i in range(1, rounds + 1)]
        lines.append(f"{name}\t{statistics.mean(values):.6f}\t"
                     f"{statistics.median(values):.6f}\t"
                     f"{statistics.median(deltas):+.3f}\t"
                     f"{sum(d > 0 for d in deltas)}/{rounds}")
        result["engines"][name] = {
            "rates": values,
            "mean_mkeys_s": statistics.mean(values),
            "paired_deltas_vs_r3_percent": deltas,
            "paired_median_vs_r3_percent": statistics.median(deltas),
            "wins_vs_r3": sum(d > 0 for d in deltas),
        }
    # Pairwise round-matched deltas across all six combinations.
    result["pairwise"] = {}
    for i, a in enumerate(IDS):
        for b in IDS[i+1:]:
            deltas = [100 * (groups[a][k] / groups[b][k] - 1)
                      for k in range(1, rounds+1)]
            result["pairwise"][f"{a}_vs_{b}"] = {
                "deltas_percent": deltas,
                "median_percent": statistics.median(deltas),
                "wins": sum(d > 0 for d in deltas),
            }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true", help="Order and catalog only; no worker execution")
    ap.add_argument("--ci-smoke", action="store_true", help="GitHub Actions only, 8-job smoke without cgroup quota")
    ap.add_argument("--jobs", type=int, default=96)
    ap.add_argument("--warmup-jobs", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--max-seconds", type=int, default=960,
                    help="Global benchmark budget, excludes build")
    ap.add_argument("--per-observation-seconds", type=int, default=180)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    check_order()
    workers = validated_catalog()
    if args.selftest:
        print("PASS: four workers from catalog, four position-balanced rounds, production default unchanged")
        return
    if args.ci_smoke and os.getenv("GITHUB_ACTIONS") != "true":
        ap.error("--ci-smoke is allowed only on GitHub Actions")
    if args.rounds != 4:
        ap.error("Four rounds required for position-balanced protocol")
    if args.jobs < (8 if args.ci_smoke else 32) or args.jobs > 256:
        ap.error("jobs must be 32..256 (8+ in CI smoke)")
    if not 0 <= args.warmup_jobs <= 32 or args.max_seconds < 60:
        ap.error("Invalid warmup/time limit")
    if cmd("uname", "-m") != "aarch64":
        ap.error("ARM64 host required")
    quota = cpu_quota(args.ci_smoke)
    for name, worker in workers.items():
        if not worker.is_file() or not os.access(worker, os.X_OK):
            ap.error(f"Worker {name} is missing; compile it first: {worker}")
        if name.startswith("r7"):
            p = subprocess.run(["strings", str(worker)], capture_output=True,
                               text=True, timeout=15, check=True)
            if "R7_STAGES worker=" in p.stdout:
                ap.error(f"Uninstrumented variant contains stage timers: {worker}")
    out = args.output.resolve() if args.output is not None else None
    if out is None:
        ap.error("--output required (new private evidence directory)")
    os.umask(0o077)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    start_meta = production_db_metadata()
    prov = {
        "source_commit": cmd("git", "-C", str(ROOT), "rev-parse", "HEAD"),
        "uname": cmd("uname", "-a"), "cpu_quota": quota,
        "seed": SEED, "puzzle_target": pool.TARGET, "chunk": pool.CHUNK,
        "jobs": args.jobs, "warmup_jobs": args.warmup_jobs,
        "rounds": args.rounds, "order": ORDER,
        "run_budget_seconds": args.max_seconds,
        "workers": {k: {"path": str(v), "sha256": sha256(v)}
                    for k, v in workers.items()},
        "real_campaign_at_start_STAT_ONLY": start_meta,
        "real_campaign_opened": False,
    }
    (out / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")
    rows = []
    began = time.monotonic()
    deadline = began + args.max_seconds
    try:
        if args.warmup_jobs:
            for ident in IDS:
                dat = observation(workers[ident], out / f"warmup-{ident}",
                                  args.warmup_jobs, deadline, args.per_observation_seconds)
                row = {"round": 0, "slot": 0, "worker": ident,
                       "phase": "warmup", **dat, "cpu_quota": quota}
                rows.append(row)
                write_table(rows, out / "results.tsv")
                print(f"warmup {ident}: {dat['mkeys_s']:.4f} Mkeys/s", flush=True)
        for rid, order in enumerate(ORDER, 1):
            for slot, ident in enumerate(order, 1):
                if cpu_quota(args.ci_smoke) != quota:
                    raise RuntimeError("Quota changed during benchmark")
                dat = observation(workers[ident], out / f"r{rid}-{slot}-{ident}",
                                  args.jobs, deadline, args.per_observation_seconds)
                rows.append({"round": rid, "slot": slot, "worker": ident,
                             "phase": "measured", **dat, "cpu_quota": quota})
                write_table(rows, out / "results.tsv")
                print(f"Round {rid}/4 slot {slot}/4 {ident}: "
                      f"{dat['mkeys_s']:.5f} Mkeys/s, {dat['elapsed_s']:.1f}s",
                      flush=True)
        make_summary(rows, args.rounds, out)
        print(f"PASS: all 16 measured observations committed to disposable SQLite, "
              f"{time.monotonic() - began:.1f}s elapsed", flush=True)
    finally:
        write_table(rows, out / "results.tsv")
        after = production_db_metadata()
        (out / "real-campaign-stat-check.json").write_text(json.dumps({
            "before": start_meta, "after": after, "same_stat": start_meta == after
        }, indent=2) + "\n")


if __name__ == "__main__":
    main()
