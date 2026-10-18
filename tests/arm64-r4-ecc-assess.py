#!/usr/bin/env python3
"""R4 rapid field-kernel screen. Never infer full Keyhunt throughput from this."""
import csv
import statistics
import sys
from pathlib import Path

if len(sys.argv)!=2:
    raise SystemExit("usage: arm64-r4-ecc-assess.py <benchmark.csv>")
p=Path(sys.argv[1])
rows=list(csv.DictReader(p.open()))
if not rows:
    raise SystemExit("No benchmark records")
groups={}
for row in rows:
    groups.setdefault(row["variant"],[]).append(float(row["field_muls_per_second"]))
baseline=groups.get("4x64")
if not baseline:
    raise SystemExit("4x64 control missing")
control=statistics.median(baseline)
print("R4 FIELD MUL ONLY: short screening; NOT a completed HASH160 worker benchmark")
print("Input includes radix conversion back to 4x64 and field reduction.")
print("Screening is directional; evaluate noise, disassembly, and correctness before promotion.")
print()
print(f"{'variant':<14} {'median Mmul/s':>15} {'vs 4x64':>12} {'passes 5%':>12}")
for name,samples in sorted(groups.items(),key=lambda item:-statistics.median(item[1])):
    ratio=statistics.median(samples)/control
    sample_wins=sum(x>control*1.05 for x in samples)
    print(f"{name:<14} {statistics.median(samples)/1e6:>15.4f} {(ratio-1)*100:>+11.2f}% {sample_wins:>5}/{len(samples):<6}")
print()
print("Next gate: ONLY winners with >5% over control, reproducible across repeats,")
print("deserve integrated point-loop experiments. Scalar/NEON negative results")
print("do not disprove a resident-limb SoA design; conversion overhead is real here.")
