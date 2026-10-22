#!/usr/bin/env python3
"""Fail-closed read-only preflight for the EXISTING Puzzle71 Keypool campaign."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote
import importlib.util

RELEASE = Path(__file__).resolve().parent
CTRL = RELEASE / "keypoold.py"
spec = importlib.util.spec_from_file_location("keypool_release", CTRL)
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)


def digest(path):
    hash_ = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            hash_.update(chunk)
    return hash_.hexdigest()


def require(cond, why):
    if not cond:
        raise RuntimeError(why)


def campaign_state(db):
    require(db.is_file(), "Existing campaign SQLite missing. REFUSE init or create.")
    # URI ro, NEVER sqlite3.connect(db) or pool.init().
    uri = "file:" + quote(str(db.resolve()), safe="/") + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM campaign WHERE id=1").fetchone()
    require(row is not None, "campaign row missing")
    state = dict(row)
    require(state["version"] == pool.ALGO, "campaign algorithm mismatch")
    require(state["target"] == pool.TARGET, "campaign target mismatch")
    require(int(state["lower"], 16) == pool.LOWER, "campaign lower bound mismatch")
    require(int(state["upper"], 16) == pool.UPPER, "campaign upper bound mismatch")
    require(state["chunk"] == pool.CHUNK, "campaign chunk size mismatch")
    require(len(state["seed"]) == 32 and
            all(c in "0123456789abcdefABCDEF" for c in state["seed"]),
            "campaign seed malformed")
    require(0 <= state["next_i"] <= pool.COUNT, "campaign cursor out of bounds")
    require(state["inflight"] is None or state["inflight"] == state["next_i"],
            "unexpected inflight cursor")
    target_file = Path(state["target_file"])
    require(target_file.is_file(), "Original target file missing")
    require(target_file.read_text(encoding="ascii").strip() == pool.TARGET,
            "original target file changed")
    require(state["found"] == 0, "campaign already completed with verified hit; don't restart")
    return {
        "completed_chunks": state["next_i"],
        "inflight": state["inflight"] is not None,
        "recovery_restarts": state["reissued"],
        "found": bool(state["found"])
    }


def check_release(db, worker_name):
    real_release = RELEASE.resolve()
    manifest_path = real_release / "release-manifest.json"
    require(manifest_path.is_file(), "missing release manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    worker = real_release / worker_name
    require(worker_name in manifest["approved_workers"],
            "worker not in release allow-list")
    require(worker.is_file() and os.access(worker, os.X_OK), "worker missing or not executable")
    require(digest(worker) == manifest["approved_workers"][worker_name],
            "worker SHA256 mismatch. Refuse silent replacement")
    require(digest(CTRL) == manifest["controller_sha256"],
            "controller SHA256 mismatch. Refuse silent replacement")
    require(digest(real_release / "keypool_preflight.py") == manifest["preflight_sha256"],
            "preflight SHA256 mismatch")
    state = campaign_state(db)
    return {
        "release_commit": manifest["source_commit"],
        "worker": worker_name,
        "worker_sha256": manifest["approved_workers"][worker_name],
        **state
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--worker", choices=[
        "keyhunt-worker-r7-ecc-fold-unprofiled",
        "keyhunt-worker-r7-ecc-pair-unprofiled",
        "keyhunt-worker-r3-ecc-sched"
    ], default="keyhunt-worker-r7-ecc-fold-unprofiled")
    args = parser.parse_args()
    try:
        data = check_release(args.db, args.worker)
    except (OSError, RuntimeError, sqlite3.Error, ValueError, KeyError) as error:
        print(f"Keypool preflight REFUSED: {error}", file=sys.stderr)
        return 1
    # Never print seed or any private key.
    print(json.dumps(data, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
