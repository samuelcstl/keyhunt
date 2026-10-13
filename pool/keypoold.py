#!/usr/bin/env python3
"""Local KISS pool for the public Bitcoin Puzzle #71. Disabled until run manually.

One SQLite campaign, one persistent four-core Keyhunt child, one in-flight job.
Jobs are deterministically shuffled and never intentionally reallocated.
After a crash the uncommitted job is replayed, never skipped.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import select
import signal
import sqlite3
import subprocess
import sys

TARGET = "1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU"
LOWER, UPPER, CHUNK = 1 << 70, 1 << 71, 1 << 20
COUNT = (UPPER - LOWER) // CHUNK  # 2^50
ALGO = "feistel50-blake2s-v1"
DEFAULT_DB = Path.home() / ".local/state/keypool/campaign.sqlite3"
DEFAULT_TARGET_FILE = (Path.home() / "BITCOIN_ANALYSIS/bitcoin-puzzle"
                       / "runs/bench71/target.txt")
DEFAULT_WORKER = Path(__file__).resolve().parents[1] / "keyhunt-worker"
SHUTDOWN = False


def permute(i: int, seed: bytes, bits: int = 50) -> int:
    """Six-round balanced Feistel: bijective on an even-bit power-of-two grid."""
    if bits < 2 or bits % 2 or i < 0 or i >= 1 << bits:
        raise ValueError("invalid permutation domain/index")
    half = bits // 2
    mask = (1 << half) - 1
    width = (half + 7) // 8
    left, right = i >> half, i & mask
    for rnd in range(6):
        digest = hashlib.blake2s(
            seed + bytes((rnd,)) + right.to_bytes(width, "big"),
            digest_size=4,
        ).digest()
        left, right = right, (left ^ int.from_bytes(digest, "big")) & mask
    return (left << half) | right


def connect(db: Path) -> sqlite3.Connection:
    if not db.is_file():
        raise RuntimeError(f"Missing campaign {db}; run 'init' first")
    c = sqlite3.connect(db, timeout=5)
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("PRAGMA synchronous=FULL")
    return c


def load(c: sqlite3.Connection) -> dict:
    c.row_factory = sqlite3.Row
    row = c.execute("SELECT * FROM campaign WHERE id=1").fetchone()
    if row is None:
        raise RuntimeError("Missing campaign row")
    state = dict(row)
    if (state["version"] != ALGO or state["target"] != TARGET or
        state["lower"] != hex(LOWER) or state["upper"] != hex(UPPER) or
        state["chunk"] != CHUNK or not 0 <= state["next_i"] <= COUNT):
        raise RuntimeError("Campaign parameters changed: refusing resume")
    return state


def assert_target(path: Path) -> None:
    if path.read_text(encoding="ascii").strip() != TARGET:
        raise RuntimeError("Target file does not contain exactly Puzzle #71")


def init(db: Path, target_file: Path) -> None:
    assert_target(target_file)
    db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(db.parent, 0o700)
    fd = os.open(db, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(fd)
    with sqlite3.connect(db) as c:
        c.execute("""CREATE TABLE campaign(
            id INTEGER PRIMARY KEY CHECK(id=1),
            version TEXT NOT NULL, target TEXT NOT NULL,
            lower TEXT NOT NULL, upper TEXT NOT NULL,
            chunk INTEGER NOT NULL, seed TEXT NOT NULL,
            next_i INTEGER NOT NULL, inflight INTEGER,
            reissued INTEGER NOT NULL DEFAULT 0,
            found INTEGER NOT NULL DEFAULT 0,
            target_file TEXT NOT NULL)""")
        c.execute(
            "INSERT INTO campaign(id,version,target,lower,upper,chunk,seed,"
            "next_i,target_file) VALUES (1,?,?,?,?,?,?,0,?)",
            (ALGO, TARGET, hex(LOWER), hex(UPPER), CHUNK,
             secrets.token_hex(16), str(target_file.resolve())),
        )
    print(f"Initialized private local campaign: {db}")


def status(db: Path) -> None:
    with connect(db) as c:
        s = load(c)
    i = s["next_i"]
    print(json.dumps({
        "target": s["target"], "completed_chunks": i,
        "unique_completed_keys": str(i * CHUNK),
        "total_chunks": COUNT, "percent": 100 * i / COUNT,
        "inflight": s["inflight"], "reissued_assignments": s["reissued"],
        "found": bool(s["found"]),
    }, indent=2))


def verify_hit(key_hex: str) -> bool:
    """Independent scalar -> compressed HASH160 -> base58check path."""
    n = int(key_hex, 16)
    order = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    if not 1 <= n < order:
        return False
    p = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
    generator = (
        0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
        0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
    )

    def add(a, b):
        if a is None:
            return b
        if b is None:
            return a
        x1, y1 = a
        x2, y2 = b
        if x1 == x2 and (y1 + y2) % p == 0:
            return None
        slope = ((3*x1*x1) * pow(2*y1, -1, p) if a == b else
                 (y2-y1) * pow((x2-x1) % p, -1, p)) % p
        x = (slope*slope-x1-x2) % p
        return x, (slope*(x1-x)-y1) % p

    point = None
    base = generator
    while n:
        if n & 1:
            point = add(point, base)
        base = add(base, base)
        n >>= 1
    if point is None:
        return False
    x, y = point
    pub = bytes((2 + (y & 1),)) + x.to_bytes(32, "big")
    digest = hashlib.new("ripemd160", hashlib.sha256(pub).digest()).digest()
    body = b"\0" + digest
    checksum = hashlib.sha256(hashlib.sha256(body).digest()).digest()[:4]
    raw = body + checksum
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    value = int.from_bytes(raw, "big")
    encoded = ""
    while value:
        value, digit = divmod(value, 58)
        encoded = alphabet[digit] + encoded
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + encoded == TARGET


def save_hit(db: Path, key: str) -> None:
    path = db.parent / "FOUND.private"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        # A crash after fsync but before the DB commit must be resumable.
        if path.read_text(encoding="ascii").strip().lower() == key.lower():
            return
        raise RuntimeError("Existing hit file differs; stop and inspect locally")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(key + "\n")
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    print(f"Verified match stored with owner-only permissions: {path}")


def terminate_on_signal(_signum, _frame):
    global SHUTDOWN
    SHUTDOWN = True


def run(db: Path, worker: Path, max_jobs: int, timeout: int) -> None:
    db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lockfd = os.open(str(db) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(lockfd)
        raise RuntimeError("Another keypool process already owns this campaign") from exc
    proc = None
    try:
        with connect(db) as c:
            s = load(c)
            if s["found"]:
                print("Campaign already has a verified match; refusing to search")
                return
            assert_target(Path(s["target_file"]))
            if s["inflight"] is not None:
                c.execute("UPDATE campaign SET reissued=reissued+1 WHERE id=1")
                c.commit()
            if not worker.is_file():
                raise RuntimeError(f"Missing worker binary: {worker}")
            seed = bytes.fromhex(s["seed"])
            logfd = os.open(db.parent / "worker.log",
                            os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(logfd, "w") as log:
                args = [str(worker.resolve()), "-m", "address", "-f",
                        s["target_file"], "-l", "compress", "-t", "4",
                        "-n", "0x40000", "-q", "-s", "0"]
                proc = subprocess.Popen(args, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=log,
                                        text=True, bufsize=1)
                processed = 0
                while s["next_i"] < COUNT and not SHUTDOWN:
                    i = s["next_i"]
                    block = permute(i, seed)
                    lo, hi = LOWER + block * CHUNK, LOWER + (block+1) * CHUNK
                    c.execute("UPDATE campaign SET inflight=? WHERE id=1", (i,))
                    c.commit()  # journal before dispatch, so crash cannot skip
                    job = json.dumps({"id": i, "start": hex(lo),
                                      "end_exclusive": hex(hi)}, separators=(",", ":"))
                    proc.stdin.write(job + "\n")
                    proc.stdin.flush()
                    readable, _, _ = select.select([proc.stdout], [], [], timeout)
                    if not readable:
                        raise RuntimeError("Worker timed out; job remains uncommitted")
                    line = proc.stdout.readline()
                    if not line:
                        raise RuntimeError("Worker ended without completing its job")
                    response = json.loads(line)
                    if response.get("id") != i or response.get("count") != CHUNK:
                        raise RuntimeError("Wrong job completion; cursor unchanged")
                    kind = response.get("type")
                    if kind == "hit":
                        secret = response.get("key", "")
                        if not isinstance(secret, str) or not verify_hit(secret):
                            raise RuntimeError("Worker reported an invalid match")
                        save_hit(db, secret)
                    elif kind != "complete":
                        raise RuntimeError("Worker returned non-completion status")
                    updated = c.execute(
                        "UPDATE campaign SET next_i=?, inflight=NULL, found=? "
                        "WHERE id=1 AND next_i=?",
                        (i + 1, int(kind == "hit"), i),
                    )
                    if updated.rowcount != 1:
                        raise RuntimeError("Unexpected database cursor")
                    c.commit()
                    s["next_i"] = i + 1
                    processed += 1
                    if kind == "hit":
                        break
                    if max_jobs and processed >= max_jobs:
                        break
                print(f"Completed {processed} jobs in this session; cursor={s['next_i']}")
    finally:
        if proc is not None:
            if proc.stdin:
                proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        os.close(lockfd)


def main():
    parser = argparse.ArgumentParser(description="Local puzzle-71 Keyhunt controller")
    parser.add_argument("command", choices=("init", "status", "run"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--target-file", type=Path, default=DEFAULT_TARGET_FILE)
    parser.add_argument("--worker", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    try:
        if args.max_jobs < 0 or args.timeout < 1:
            raise ValueError("Invalid limits")
        if args.command == "init":
            init(args.db, args.target_file)
        elif args.command == "status":
            status(args.db)
        else:
            signal.signal(signal.SIGTERM, terminate_on_signal)
            signal.signal(signal.SIGINT, terminate_on_signal)
            run(args.db, args.worker, args.max_jobs, args.timeout)
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"keypool: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
