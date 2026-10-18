#!/usr/bin/env python3
"""R9 balanced full-pipeline output with one real four-lane HASH160 consumer."""
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path
if len(sys.argv)!=2:raise SystemExit("usage: arm64-r9-pipeline-assess.py results.csv")
observations=defaultdict(list)
for row in csv.DictReader(Path(sys.argv[1]).open()):
    p=int(row["producers"]);w=int(row["width"])
    if row["produced_keys"]!=row["hashed_keys"]:
        raise SystemExit(f"ERROR: producer/consumer key mismatch {p}p-W{w}")
    if int(row["peak_packets"])>int(row["queue"]):
        raise SystemExit("ERROR: unbounded packet queue")
    observations[(p,w)].append(row)
print("PHYSICAL full indexed ECC producer→four-way compressed HASH160 consumer")
print("Threads=producer count+1. 4-core Keyhunt control must be separately A/B tested.")
print("Wait shares are cumulative queue time, not precise OS scheduling idle.")
print()
print(f"{'P':>2} {'W':>3} {'Mhash/s':>11} {'hash busy%':>11} {'consumer empty%':>16} {'producer full%':>15} {'queue peak':>11}")
for (p,w),rows in sorted(observations.items()):
    def med(fn):return statistics.median(fn(r) for r in rows)
    rate=med(lambda r:float(r["hashed_Mkeys_s"]))
    busy=med(lambda r:float(r["consumer_hash_ms"])/max(float(r["elapsed_s"])*1000,1)*100)
    empty=med(lambda r:float(r["queue_empty_ms"])/max(float(r["elapsed_s"])*1000,1)*100)
    full=med(lambda r:float(r["queue_full_ms"])/max(float(r["elapsed_s"])*1000,1)*100)
    maxqueue=max(int(r["peak_packets"]) for r in rows)
    print(f"{p:>2} {w:>3} {rate:>11.4f} {busy:>10.1f}% {empty:>15.1f}% {full:>14.1f}% {maxqueue:>11}")
print()
if (1,16) in observations and (3,16) in observations:
    solo=statistics.median(float(r["hashed_Mkeys_s"]) for r in observations[(1,16)])
    multi=statistics.median(float(r["hashed_Mkeys_s"]) for r in observations[(3,16)])
    print(f"Three ECC producer sources vs one, W16, 4 total threads: {(multi/solo-1)*100:+.2f}%")
print("Proof against R3 4-core still needs a matched baseline; never assume a throughput gain.")
