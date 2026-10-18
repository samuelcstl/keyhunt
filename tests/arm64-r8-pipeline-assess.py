#!/usr/bin/env python3
"""R8 actual producer->consumer capacity sweep: do not conflate 2 threads with 4-core Keyhunt."""
import csv
import statistics
import sys
from pathlib import Path
from collections import defaultdict
if len(sys.argv)!=2: raise SystemExit("usage: arm64-r8-pipeline-assess.py results.csv")
data=defaultdict(list)
with Path(sys.argv[1]).open() as f:
    for x in csv.DictReader(f):
        if x["mode"] != "bench": raise RuntimeError("Unexpected verify benchmark")
        if x["produced_keys"] != x["hashed_keys"]:
            raise RuntimeError("ECC/HASH160 mismatch")
        if int(x["peak_packets"])>int(x["queue"]): raise RuntimeError("Queue overflow")
        data[int(x["width"])].append(x)
if not data.get(1): raise RuntimeError("Missing W1 comparison")
print("REAL ECC(affine inverse, X/Y) producer -> bounded ring -> 4-way HASH160 consumer")
print("One producer and one consumer thread, NOT comparable to existing 4-core Keyhunt Mkeys/s.")
print("Results include actual HASH160 target compare, exact logical key accounting.")
print("Queue backpressure/empty milliseconds are summed across producer or consumer.")
print()
head=f"{'width':>5} {'med Mhash/s':>13} {'vs W=1':>10} {'queue full%':>12} {'queue empty%':>13} {'pkts max':>9}"
print(head)
control=statistics.median(float(x["hashed_Mkeys_s"]) for x in data[1])
for width,rows in sorted(data.items()):
    rate=statistics.median(float(x["hashed_Mkeys_s"]) for x in rows)
    full=statistics.median(float(x["queue_full_ms"])/max(1, float(x["elapsed_s"])*1000)*100 for x in rows)
    empty=statistics.median(float(x["queue_empty_ms"])/max(1, float(x["elapsed_s"])*1000)*100 for x in rows)
    print(f"{width:>5} {rate:>13.4f} {(rate/control-1)*100:>+9.2f}% {full:>11.1f}% {empty:>12.1f}% {max(int(x['peak_packets']) for x in rows):>9}")
print()
print("Producer bottleneck: long consumer EMPTY wait. Hash bottleneck: producer FULL queue wait.")
print("Includes mutex/copy/mapping overhead; a stage bottleneck must not be assumed from MUL microbench.")
