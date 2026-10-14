#!/usr/bin/env python3
"""Compare every recovered upstream puzzle key, across many ECC group boundaries.

Both builds use the same SHA256SU0/SU1 + NEON RIPEMD160 backend. Only
KEYHUNT_INCREMENTAL_CENTER differs. This catches point-skips/duplicates
after group boundaries, not just first-group known-key recovery.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
binaries=("keyhunt-arm64-sha2-neon-su2",
          "keyhunt-arm64-sha2-neon-su2-center")
target=root/"tests"/"1to32.txt"

def run(exe, temp):
    args=[str(root/exe), "-m","address","-f",str(target),
          "-r","1:40000","-n","0x400","-l","compress",
          "-t","1","-q","-s","0"]
    cp=subprocess.run(args,cwd=temp,text=True,stdout=subprocess.PIPE,
                      stderr=subprocess.STDOUT,timeout=60,check=False)
    if cp.returncode != 0:
        raise RuntimeError(f"{exe}: returned {cp.returncode}:\n{cp.stdout[-5000:]}")
    found=[int(x,16) for x in re.findall(
        r"Hit! Private Key:\s*([0-9a-fA-F]+)",cp.stdout)]
    return found,cp.stdout

def main():
    results=[]
    with tempfile.TemporaryDirectory(prefix="keyhunt-center-compare-") as tmp:
        temp=Path(tmp)
        for binary in binaries:
            hitlist,output=run(binary,temp)
            if not hitlist:
                raise AssertionError(f"{binary} did not recover any keys\n"+output[-1500:])
            results.append(hitlist)
    if results[0] != results[1]:
        raise AssertionError("ECC center reuse changed recovered keys or order:\n"
                             f"baseline: {results[0]}\ncenter: {results[1]}")
    expected=[1,3,7,8,0x15,0x31,0x4c,0xe0,0x1d3,
              0x202,0x483,0xa7b,0x1460,0x2930]
    missing=set(expected)-set(results[0])
    if missing:
        raise AssertionError(f"Expected solved puzzle keys missing: {sorted(missing)}")
    print(f"PASS: ECC center continuity, {len(results[0])} identical solved-key hits")
    print("PASS: recovered keys include 0x2930, beyond ten 1024-point groups")

if __name__=="__main__":
    main()
