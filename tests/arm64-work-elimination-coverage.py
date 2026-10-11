#!/usr/bin/env python3
"""Parity-field work-elimination probes: retain exact key coverage.

Checks both the fast single-target path and its multi-target fallback;
strictly compares recovered private-key order with the proven control.
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parent.parent
BINARIES=(
    "keyhunt-arm64-sha2-neon-su2-center-parity-field-mul-sqr",
    "keyhunt-arm64-sha2-neon-su2-center-parity-field-point",
    "keyhunt-arm64-sha2-neon-su2-center-parity-field-direct1",
    "keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1",
)

def scan(binary, work):
    args=[str(ROOT/binary),"-m","address","-f",str(ROOT/"tests"/"1to32.txt"),
          "-r","1:40000","-n","0x2000","-l","compress",
          "-t","1","-q","-s","0"]
    result=subprocess.run(args,cwd=work,text=True,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,timeout=70,check=False)
    if result.returncode:
        raise AssertionError(f"{binary}: exit={result.returncode}\n{result.stdout[-3500:]}")
    return [int(k,16) for k in re.findall(
        r"Hit! Private Key:\s*([0-9a-fA-F]+)",result.stdout)]

def main():
    with tempfile.TemporaryDirectory(prefix="keyhunt-avoid-work-") as td:
        outcomes={name:scan(name,Path(td)) for name in BINARIES}
    expected=outcomes[BINARIES[0]]
    if len(expected)!=18:
        raise AssertionError(f"Unexpected baseline number of solved puzzle keys: {expected}")
    for name,actual in outcomes.items():
        if actual!=expected:
            raise AssertionError(f"{name} changed key recovery\n"
                                 f"expected={expected}\nactual={actual}")
    print(f"PASS: all {len(BINARIES)} variants recovered the same 18 solved keys")
    print("PASS: direct-single-target variants fall back correctly for 18 targets")

if __name__=="__main__":
    main()
