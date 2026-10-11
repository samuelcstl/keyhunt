#!/usr/bin/env python3
"""Cross-variant recovered-key identity/continuity on solved BTC puzzle fixtures.

No benchmark speed assumptions. Exercise >10 1024-key group boundaries and
both actual public-key parities; compare exact recovered private-key values.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
names=(
    "keyhunt-arm64-sha2-neon-su2-center",
    "keyhunt-arm64-sha2-neon-su2-center-parity",
    "keyhunt-arm64-sha2-neon-su2-center-512",
    "keyhunt-arm64-sha2-neon-su2-center-2048",
)

def scan(binary, working_dir):
    process=subprocess.run([
        str(root/binary), "-m","address", "-f",str(root/"tests"/"1to32.txt"),
        "-r","1:40000", "-n","0x2000", "-l","compress",
        "-t","1", "-q","-s","0"
    ],cwd=working_dir,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
      text=True,timeout=65,check=False)
    if process.returncode:
        raise AssertionError(f"{binary} exited {process.returncode}:\n{process.stdout[-4500:]}")
    return [int(v,16) for v in re.findall(r"Hit! Private Key:\s*([0-9a-fA-F]+)",process.stdout)]

def main():
    seen={}
    with tempfile.TemporaryDirectory(prefix="keyhunt-ecc-parity-") as tmp:
        for name in names:
            result=scan(name,Path(tmp))
            if not result:
                raise AssertionError(f"{name}: no keys recovered")
            seen[name]=result
            print(f"{name}: {len(result)} recovered solved keys")
    reference=seen[names[0]]
    for name in names[1:]:
        if seen[name] != reference:
            raise AssertionError(f"Recovered keys changed with {name}:\n"
                f"baseline={reference}\nvariant={seen[name]}")
    necessary={1,3,7,8,0x15,0x31,0x4c,0xe0,0x1d3,
               0x202,0x483,0xa7b,0x1460,0x2930}
    missing=necessary-set(reference)
    if missing:
        raise AssertionError(f"Missing expected solved keys: {sorted(missing)}")
    print(f"PASS: {len(reference)} identical solved private keys across all 4 variants")
    print("PASS: all variants crossed 512/1024/2048-point group boundaries")

if __name__=="__main__":
    main()
