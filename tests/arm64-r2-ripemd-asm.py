#!/usr/bin/env python3
"""Inspect actual AArch64 RIPEMD160 inlined machine-code rotations.

The concrete binary is the contract. Objdump is authoritative, not source
intrinsic counts. In this project the NEON4 function is LTO-inlined into
Secp256K1::GetHash160_fromXYParityTarget.
"""
from collections import Counter
from pathlib import Path
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HEADER = re.compile(r"^[0-9a-f]+ <([^>]+)>:$",re.MULTILINE)
INSN = re.compile(r"^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+([a-z][a-z0-9.]*)\b",re.MULTILINE)
ROTATIONS = ("shl","ushr","orr","sli","sri","usra")

def inspect(path):
    try:
        output = subprocess.check_output(["objdump","-drwC",str(path)],
                                         text=True,stderr=subprocess.STDOUT)
    except (OSError,subprocess.CalledProcessError) as exc:
        raise SystemExit(f"objdump failed for {path}: {exc}")
    spans=list(HEADER.finditer(output))
    matches=[]
    for i,m in enumerate(spans):
        if not m.group(1).startswith("Secp256K1::GetHash160_fromXYParityTarget("):
            continue
        end=spans[i+1].start() if i+1<len(spans) else len(output)
        matches.append((m.group(1),output[m.end():end]))
    if len(matches)!=1:
        raise SystemExit(f"{path}: expected one target HASH160 symbol; found {len(matches)}")
    symbol,asm=matches[0]
    counts=Counter(INSN.findall(asm))
    return {
        "binary":path.name, "symbol":symbol,
        "total_instructions":sum(counts.values()),
        "rotation_related":{m:counts[m] for m in ROTATIONS},
        "insertion_instructions":counts["sli"]+counts["sri"],
        "note":"Includes wrapper, SHA handoff, and RIPEMD160; not all shifts belong to rotate"
    }

if __name__=="__main__":
    if len(sys.argv)<3:
        raise SystemExit("usage: arm64-r2-ripemd-asm.py <control> <candidate> [...]")
    results=[inspect(ROOT/p) for p in sys.argv[1:]]
    for r in results:
        print(json.dumps(r,indent=2))
    control=results[0]
    for r in results[1:]:
        if r["insertion_instructions"] == 0:
            print(f"WARNING {r['binary']}: no SLI/SRI in function; no codegen-level rotate advantage verified",file=sys.stderr)
        else:
            print(f"CODEGEN {r['binary']}: {r['insertion_instructions']} SLI/SRI in target HASH160 routine")
