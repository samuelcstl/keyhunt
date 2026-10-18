#!/usr/bin/env python3
"""R8 affine batch inversion capacity in complete 513-denominator batches."""
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path
if len(sys.argv)!=2:
    raise SystemExit("usage: arm64-r8-affine-assess.py benchmark.csv")
rows=list(csv.DictReader(Path(sys.argv[1]).open()))
rates=defaultdict(list)
for row in rows:
    rates[int(row["width"])].append(float(row["batches_per_second"]))
if 0 not in rates:
    raise SystemExit("Missing original IntGroup control")
control=statistics.median(rates[0])
print("ONE inverse per 513-element affine batch at every width")
print("W=0 is original IntGroup; W>0 segmented prefix/suffix with independent chains")
print("Rate is complete batches/s, NOT points/s nor BTC keys/s.")
print()
print(f"{'width':>8} {'batches/s':>15} {'vs original':>14} {'513 inverses/s':>16}")
for width,rr in sorted(rates.items()):
    median=statistics.median(rr)
    print(f"{width:>8} {median:>15.1f} {(median/control-1)*100:>+13.2f}% {median*513:>16.0f}")
print()
print("Differential equality and x*inverse(x)=1 must PASS before any speed result.")
print("An inversion-stage win does not prove improved full ECC->HASH160 throughput.")
