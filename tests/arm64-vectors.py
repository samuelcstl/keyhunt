#!/usr/bin/env python3
"""Independent secp256k1/address vectors for the ARM64 Keyhunt port.

Uses only Python's big integers and standard hashlib, deliberately avoiding
Keyhunt's ECC and hashing code. Each synthetic address is searched in a short
range that includes its known private scalar. Exercises both compressed point
parities and scalars with 71, 140 and ~256 significant bits.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    x1, y1 = a
    x2, y2 = b
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if a == b:
        slope = ((3 * x1 * x1) * pow(2 * y1, -1, P)) % P
    else:
        slope = ((y2 - y1) * pow((x2 - x1) % P, -1, P)) % P
    x3 = (slope * slope - x1 - x2) % P
    return x3, (slope * (x1 - x3) - y1) % P


def mul(k):
    result = None
    base = G
    while k:
        if k & 1:
            result = add(result, base)
        base = add(base, base)
        k >>= 1
    return result


def btc_address(k):
    point = mul(k)
    if point is None:
        raise AssertionError("invalid scalar")
    x, y = point
    compressed = bytes((2 + (y & 1),)) + x.to_bytes(32, "big")
    digest = hashlib.new(
        "ripemd160", hashlib.sha256(compressed).digest()
    ).digest()
    body = b"\x5cx00" + digest
    check = hashlib.sha256(hashlib.sha256(body).digest()).digest()[:4]
    value = int.from_bytes(body + check, "big")
    encoded = ""
    while value:
        value, rem = divmod(value, 58)
        encoded = ALPHABET[rem] + encoded
    leading = len(body + check) - len((body + check).lstrip(b"\x5cx00"))
    return "1" * leading + encoded, y & 1


def run_vector(exe, name, key, directory):
    address, parity = btc_address(key)
    start = max(1, key - 512)
    end = min(N, key + 1536)
    target = directory / f"{name}.txt"
    target.write_text(address + "\n", encoding="utf-8")
    args = [
        str(exe), "-m", "address", "-f", str(target),
        "-r", f"{start:x}:{end:x}", "-n", "0x400",
        "-l", "compress", "-t", "1", "-q", "-s", "0",
    ]
    result = subprocess.run(
        args, cwd=directory, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=35, check=False,
    )
    needle = f"Hit! Private Key: {key:x}".lower()
    if result.returncode != 0 or needle not in result.stdout.lower():
        raise AssertionError(
            f"{name}: failed for {key:x}, parity={parity}\n"
            + result.stdout[-5000:]
        )
    if f"Address {address}" not in result.stdout:
        raise AssertionError(f"{name}: wrong address in output")
    print(f"PASS {name}: scalar bits={key.bit_length()}, parity={parity}")


def main():
    exe = (Path(__file__).resolve().parent.parent / "keyhunt-arm64").resolve()
    if not exe.is_file():
        raise SystemExit("Build keyhunt-arm64 first")
    # Check our independent implementation against the published puzzle #20.
    assert btc_address(0xD2C55)[0] == "1HsMJxNiV7TLxmoF6uJNkydxPFDog4NQum"

    even = odd = None
    for delta in range(256, 320):
        k = (1 << 70) + delta
        _, parity = btc_address(k)
        if parity == 0 and even is None:
            even = k
        if parity == 1 and odd is None:
            odd = k
        if even is not None and odd is not None:
            break
    assert even is not None and odd is not None

    cases = (
        ("puzzle71_even", even),
        ("puzzle71_odd", odd),
        ("puzzle140_range", (1 << 139) + 0x6A2),
        ("high_scalar", N - 0x10000),
    )
    with tempfile.TemporaryDirectory(prefix="keyhunt-arm64-vectors-") as tmp:
        directory = Path(tmp)
        for name, scalar in cases:
            run_vector(exe, name, scalar, directory)


if __name__ == "__main__":
    main()
