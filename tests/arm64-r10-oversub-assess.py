#!/usr/bin/env python3
"""Summarize 2-12 software-thread physical ECC/HASH160 capacity fairly."""
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

if len(sys.argv)!=2:
    raise SystemExit("usage: arm64-r10-oversub-assess.py measurements/results.csv")
series=defaultdict(list)
with Path(sys.argv[1]).open() as fh:
    for row in csv.DictReader(fh):
        p,c,w=map(lambda k:int(row[k]), ("producers","consumers","width"))
        if int(row["produced_keys"])!=int(row["hashed_keys"]):
            raise SystemExit(f"Producer/hash key loss at {p} producers, {c} consumers")
        if int(row["peak_packets"])>int(row["queue"]):
            raise SystemExit("Unbounded ring")
        series[(p,c,w)].append(row)
if not series:
    raise SystemExit("Empty R10 benchmark")
print("Actual secp256k1 ECC producers -> bounded MPMC queue -> real 4-way HASH160 consumers")
print("Each consumer has an independent 4-lane SHA2/RIPEMD160 engine.")
print("Fractions below normalize aggregated wait/busy milliseconds by THREAD count × wall seconds.")
print("Time counters include scheduler/predicate overhead; they are not pure OS blocked time.")
print()
print("P C W  Threads   Mhash/s   R1    Hash CPU%  Empty%/hash-thread  Full%/ecc-thread  Peak")
ref=(1,1,next(iter(series))[2])
control=statistics.median(float(r["hashed_Mkeys_s"]) for r in series.get(ref, []))
for (p,c,w), rows in sorted(series.items()):
    def med(field):
        return statistics.median(float(x[field]) for x in rows)
    rate=med("hashed_Mkeys_s")
    elapsed=med("elapsed_s")*1000
    busy=med("consumer_hash_ms")/(c*elapsed)*100
    empty=med("queue_empty_ms")/(c*elapsed)*100
    full=med("queue_full_ms")/(p*elapsed)*100
    peak=max(int(x["peak_packets"]) for x in rows)
    win=100*(rate/control-1) if control else 0
    print(f"{p:1d} {c:1d} {w:2d} {p+c:8d} {rate:9.4f} {win:+5.1f}%"
          f" {busy:9.1f}% {empty:16.1f}% {full:16.1f}% {peak:5d}")
print()
print("Only same-machine, same-W runs with full warm sustained windows are comparable.")
print("More threads can improve masking bursty stage delays, but cannot add arithmetic cores.")
print("For real production qualification, compare against four-core R3 under matched clocks and loads.")
