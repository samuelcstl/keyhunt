#!/usr/bin/env python3
"""Cross-check the field multiplication/squaring reducer against Python bigint.

Covers 0, 1, 2, p-1, p-2, values at word boundaries and deterministic
high-entropy samples. Test vectors are independent of Keyhunt.
"""
import random
import subprocess
from pathlib import Path

P=(1<<256)-(1<<32)-977
ROOT=Path(__file__).resolve().parent.parent
R=random.Random(0x71_2026_10_11)

edges=[0,1,2,3,4,5,(1<<32)-1,1<<32,(1<<64)-1,
       1<<64,(1<<128)-1,1<<128,(1<<192)-1,1<<192,
       (1<<255), P-1,P-2,P-3,P-4,P-5,P-(1<<32),
       (1<<256)-(1<<32)-978]
edges=[x for x in edges if 0 <= x < P]
pairs=[(a,b) for a in edges for b in edges]
pairs.extend((R.randrange(P),R.randrange(P)) for _ in range(2000))
lines=[];expected=[]
for a,b in pairs:
    lines.append(f"MUL {a:x} {b:x}")
    expected.append((a*b)%P)
for a in edges:
    lines.append(f"SQR {a:x}")
    expected.append((a*a)%P)
for _ in range(2000):
    a=R.randrange(P)
    lines.append(f"SQR {a:x}")
    expected.append((a*a)%P)

run=subprocess.run([str(ROOT/"build/arm64/field-k1-check")],
    input="\n".join(lines)+"\n",text=True,stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,timeout=60,check=False)
if run.returncode:
    raise AssertionError(f"Field checker exited {run.returncode}: {run.stderr[-4000:]}")
got=run.stdout.splitlines()
if len(got)!=len(expected):
    raise AssertionError(f"Wrong number of field outputs: {len(got)} vs {len(expected)}")
for i,(actual,want) in enumerate(zip(got,expected)):
    if int(actual,16)!=want:
        raise AssertionError(f"Field test {i} failed: {lines[i]} "
            f"expected={want:x}, got={actual}")
print(f"PASS: {len(expected)} independent secp256k1 field multiplication/squaring vectors")
