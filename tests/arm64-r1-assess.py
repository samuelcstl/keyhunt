#!/usr/bin/env python3
"""Assess R1 Pi observations without cherry-picking or automatic promotion."""
import argparse
import csv
import json
from pathlib import Path
import re
import statistics

BASE = "keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1-neon"

def load(path):
    with path.open(newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))

def median(values):
    return statistics.median(values) if values else None

def percent(a, b):
    return 100.0*(a/b-1.0)

def throttle(value):
    found = re.search(r"throttled=0x([0-9a-fA-F]+)",str(value))
    return int(found.group(1), 16) if found else None

def clock(value):
    found = re.search(r"=(\d+)",str(value))
    return int(found.group(1)) if found else None

def sensors(samples):
    flags=[throttle(r["throttled"]) for r in samples]
    mhz=[clock(r["arm_frequency"]) for r in samples]
    issues=[]
    if not flags or any(f is None for f in flags):
        issues.append("unavailable throttle observation")
    else:
        if any(f & 0xF for f in flags):
            issues.append("active throttling")
        if (flags[-1] & 0xF0000) & ~(flags[0] & 0xF0000):
            issues.append("new sticky throttle latch")
    if not mhz or any(x is None for x in mhz):
        issues.append("unavailable ARM clock")
    elif max(mhz)-min(mhz) > 0.03 * median(mhz):
        issues.append("ARM clock variation >3%")
    return issues

def assess(folder):
    paths=list((folder/"standalone").glob("*/results.tsv"))
    if len(paths) != 1:
        raise ValueError(f"expected exactly one standalone results.tsv, got {paths}")
    rows=load(paths[0])
    workers=load(folder/"worker/paired/results.tsv")
    reports=[]
    quality=[]
    for row in rows:
        stem=paths[0].parent/f"{row['variant']}-t{row['threads']}-r{row['run']}.thermal.tsv"
        obs=sensors(load(stem)) if stem.exists() else ["thermal monitor missing"]
        rate=float(row["keys_per_second"])
        if rate <= 0:
            obs.append("zero/negative throughput")
        early=float(row["first_half_rate"])
        late=float(row["second_half_rate"])
        if early <= 0 or abs(percent(late,early))>3:
            obs.append("early/late throughput drift >3%")
        if obs:
            quality.append({"variant":row["variant"],"threads":row["threads"],
                            "rep":row["run"],"issues":obs})
    threads=sorted({int(r["threads"]) for r in rows})
    for n in threads:
        subset=[r for r in rows if int(r["threads"])==n]
        baselines={int(r["run"]):r for r in subset if r["variant"]==BASE}
        names=sorted({r["variant"] for r in subset if r["variant"]!=BASE})
        for name in names:
            candidates={int(r["run"]):r for r in subset if r["variant"]==name}
            reps=sorted(set(baselines)&set(candidates))
            if not reps or len(reps)!=len(baselines) or len(reps)!=len(candidates):
                raise ValueError(f"missing paired repetition for {name}, threads={n}")
            deltas=[percent(float(candidates[i]["keys_per_second"]),
                            float(baselines[i]["keys_per_second"])) for i in reps]
            report={"threads":n,"candidate":name,"pairs":len(reps),
                    "paired_gains_pct":deltas,"median_gain_pct":median(deltas),
                    "wins":sum(x>0 for x in deltas)}
            if all(baselines[i].get("cycles") and candidates[i].get("cycles") for i in reps):
                # Approximate: source script extrapolates native 5-second
                # status snapshots to the complete perf-stat observation.
                cyc=[percent(float(candidates[i]["cycles"])/float(candidates[i]["approx_keys_full_window"]),
                             float(baselines[i]["cycles"])/float(baselines[i]["approx_keys_full_window"]))
                     for i in reps]
                report["approx_cycles_per_key_deltas_pct"]=cyc
                report["approx_cycles_per_key_median_pct"]=median(cyc)
            reports.append(report)
    by_rep={}
    for r in workers:
        key=int(r["rep"])
        by_rep.setdefault(key,[]).append(r)
        issues=[]
        values=[throttle(r["throttle_before"]),throttle(r["throttle_after"])]
        if any(v is None for v in values):
            issues.append("worker throttle sample unavailable")
        elif (values[0]&0xF) or (values[1]&0xF) or ((values[1]&0xF0000)&~(values[0]&0xF0000)):
            issues.append("worker throttled or newly latched")
        clocks=[clock(r["clock_before"]),clock(r["clock_after"])]
        if any(c is None for c in clocks):
            issues.append("worker clock sample unavailable")
        elif abs(clocks[1]-clocks[0])>0.03*sum(clocks)/2:
            issues.append("worker clock drift >3%")
        if issues:
            quality.append({"worker":r["worker"],"rep":key,"issues":issues})
    ws=[]
    for rep,pair in sorted(by_rep.items()):
        if len(pair)!=2 or pair[0]["worker"]==pair[1]["worker"]:
            raise ValueError(f"invalid worker pairing in repetition {rep}")
        if pair[0]["keys"]!=pair[1]["keys"]:
            raise ValueError(f"different completed keys in repetition {rep}")
        control=next((r for r in pair if r["worker"]=="keyhunt-worker"),None)
        candidate=next((r for r in pair if r["worker"]=="keyhunt-worker-r1"),None)
        if control is None or candidate is None:
            raise ValueError(f"unexpected worker pair {pair}")
        ws.append(percent(float(candidate["mkeys_s"]),float(control["mkeys_s"])))
    if not ws:
        raise ValueError("worker observations missing")
    output={"quality_status":"CHECK" if not quality else "REVIEW_REQUIRED",
            "quality_findings":quality,"standalone_pairs":reports,
            "worker_pairs":{"n":len(ws),"gains_pct":ws,
                            "median_gain_pct":median(ws),"wins":sum(x>0 for x in ws)},
            "decision":"UNQUALIFIED: physical Pi quality, repeatability and disassembly need review",
            "note":"Standalone PMU/key is approximate; worker rates count completed full scalar checks."}
    (folder/"assessment.json").write_text(json.dumps(output,indent=2)+"\n")
    print(json.dumps(output,indent=2))
    return 0

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("evidence_directory",type=Path)
    args=p.parse_args()
    return assess(args.evidence_directory.resolve())

if __name__=="__main__":
    raise SystemExit(main())
