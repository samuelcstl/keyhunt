#!/usr/bin/env python3
"""R7 point-pair pipeline stage attribution from per-worker traces.

R7_STAGES data sums three measured wall-clock phase durations across
four concurrent worker threads. Report *fractions* only, NOT standalone
elapsed process seconds or CPU cycles.
"""
from pathlib import Path
import re
import sys
from collections import defaultdict

if len(sys.argv)!=2:
    raise SystemExit("usage: arm64-r7-stage-assess.py <workers-parent>")
parent=Path(sys.argv[1])
pattern=re.compile(
    r"R7_STAGES worker=(\d+) batches=(\d+) inverse_ns=(\d+) "
    r"points_ns=(\d+) hash_scan_ns=(\d+)"
)
out={}
for treatment in ("sched","pair","fold"):
    root=parent/treatment
    batches=inv=points=hashscan=0
    count=0
    for logfile in sorted(root.glob("r*-keyhunt-worker-r7-ecc-*/worker.log")):
        found=list(pattern.finditer(logfile.read_text(errors="replace")))
        if not found:
            raise SystemExit(f"No stage counters in {logfile}")
        for m in found:
            count+=1
            batches+=int(m.group(2))
            inv+=int(m.group(3))
            points+=int(m.group(4))
            hashscan+=int(m.group(5))
    if not count or not batches:
        raise SystemExit(f"Missing R7 stage counters for {treatment} under {root}")
    total=inv+points+hashscan
    out[treatment]=(count,batches,inv,points,hashscan,total)
print("candidate\tthreads_observed\tbatches\tinverse_pct\tpoint_xy_pct\thash_scan_pct\tns_per_group_sum")
for name,(count,batches,inv,points,hashscan,total) in out.items():
    print(f"{name}\t{count}\t{batches}\t{inv/total*100:.2f}\t"
          f"{points/total*100:.2f}\t{hashscan/total*100:.2f}\t{total//batches}")
