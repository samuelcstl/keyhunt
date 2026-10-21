#!/usr/bin/env python3
"""Interpret R5 two-lane, eight-deep field MUL screening, not Bitcoin keys/s."""
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

if len(sys.argv)!=2:
    raise SystemExit("usage: arm64-r5-ecc-assess.py benchmark.csv")
rows=list(csv.DictReader(Path(sys.argv[1]).open()))
grouped=defaultdict(list)
for r in rows:
    grouped[r["variant"]].append(float(r["muls_per_second"]))
baseline=statistics.median(grouped["4x64-ref"])
print("R5: complete modular field MULTIPLICATIONS/s, two independent")
print("chains of eight. NEON 10x26 stays resident between operations,")
print("with one conversion in and one canonical conversion out per chain.")
print("This does NOT measure scalar candidate keys/s or full Keypool.")
print()
print(f"{'variant':<20} {'Mmul/s median':>13} {'vs native':>12}")
for name, samples in sorted(grouped.items(), key=lambda x:-statistics.median(x[1])):
    rate=statistics.median(samples)
    print(f"{name:<20} {rate/1e6:>13.4f} {(rate/baseline-1)*100:>+11.2f}%")
print()
print("Promote nothing on 1-second samples alone. Shortlist a >5%")
print("candidate only if repeated wins survive CI and physical Pi,")
print("then benchmark its full ECC point generator with scratch chunks.")
