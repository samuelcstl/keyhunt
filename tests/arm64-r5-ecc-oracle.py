#!/usr/bin/env python3
"""Independent Python-bigint field oracle for R5 eight-stage chains.

The native 4x64 result is NOT treated as the expected value: every
variant, including the control, is compared against Python modulo p.
"""
import csv
import io
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "build/arm64/ecc-r5-chains"
P = (1 << 256) - (1 << 32) - 977
cases = int(os.getenv("KEYHUNT_R5_ORACLE_CASES", "256"))
run = subprocess.run(
    [str(EXE), "--oracle-vectors", str(cases)],
    text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    timeout=60, check=True
)
count = 0
variants = set()
for row in csv.DictReader(io.StringIO(run.stdout)):
    x = int(row["start"], 16)
    y = int(row["factor"], 16)
    got = int(row["result"], 16)
    if not (0 <= x < P and 0 <= y < P and 0 <= got < P):
        raise AssertionError(f"Noncanonical field residue {row}")
    want = x * pow(y, 8, P) % P
    if got != want:
        raise AssertionError(f"{row['variant']} lane={row['lane']} failed: {got:064x} != {want:064x}")
    variants.add(row["variant"])
    count += 1
assert len(variants) == 5, variants
assert count == cases * 2 * 5, (count, cases)
print(f"PASS: {count} independent Python bigint 8×MUL chains, all 5 kernels")
