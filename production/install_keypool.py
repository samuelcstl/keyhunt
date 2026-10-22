#!/usr/bin/env python3
"""Install a pinned, immutable Keypool release and DISABLED user systemd units.

Does NOT start/enable a service, create or migrate the existing SQLite campaign.
Refuses deployment if an existing service is enabled or active.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = Path.home() / ".local/share/keypool"
RELEASES = BASE / "releases"
CURRENT = BASE / "current"
UNITS = Path.home() / ".config/systemd/user"
DB = Path.home() / ".local/state/keypool/campaign.sqlite3"
WORKERS = (
    "keyhunt-worker-r7-ecc-fold-unprofiled",
    "keyhunt-worker-r7-ecc-pair-unprofiled",
    "keyhunt-worker-r3-ecc-sched",
)
FILES = {
    "keypoold.py": ROOT / "pool/keypoold.py",
    "keypool_preflight.py": ROOT / "production/keypool_preflight.py",
    "keypool_health.py": ROOT / "production/keypool_health.py",
}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def command(argv, *, check=True, env=None):
    return subprocess.run(argv, cwd=ROOT, env=env, text=True,
                          capture_output=True, check=check)


def source_commit():
    out = command(["git", "rev-parse", "HEAD"]).stdout.strip()
    if len(out) != 40:
        raise RuntimeError("Invalid repository commit")
    if command(["git", "status", "--porcelain", "--untracked-files=no"]).stdout.strip():
        raise RuntimeError("Tracked source modifications: refuse unpinned build")
    return out


def assert_user_service_inactive():
    proc = command(["systemctl", "--user", "show", "keypool-hunt.service",
                    "--property=ActiveState", "--value"], check=False)
    if proc.returncode:
        # A first install has no unit to inspect. Only that exact condition
        # is safe to treat as inactive; an unavailable user bus is NOT.
        problem = (proc.stderr + proc.stdout).lower()
        if "could not be found" in problem or "not found" in problem:
            state = "inactive"
        else:
            raise RuntimeError("Cannot check user systemd state. Log in as the Pi user first.")
    else:
        state = proc.stdout.strip()
    if state not in ("inactive", "failed"):
        raise RuntimeError("Existing Keypool service state is " + repr(state) +
                           ". Stop it manually before deployment.")
    enabled = command(["systemctl", "--user", "is-enabled",
                       "keypool-hunt.service"], check=False)
    if enabled.stdout.strip() not in ("disabled", "not-found", "static", "masked", ""):
        raise RuntimeError("Service is enabled: disable it manually before changing releases")
    if enabled.stdout.strip() == "masked":
        raise RuntimeError("Service masked; refuse to alter controls")


def test_worker(worker):
    env = os.environ.copy()
    for key in ("KEYHUNT_R7_STAGE_PROFILE", "KEYHUNT_WORKER_TRACE",
                "KEYHUNT_WORKER_COVERAGE"):
        env.pop(key, None)
    env["KEYHUNT_WORKER_BIN"] = worker
    for script in ("tests/arm64-worker-protocol.py",
                   "tests/keypool-puzzle20-exhaustive.py"):
        result = command([sys.executable, str(ROOT / script)], env=env, check=False)
        if result.returncode:
            raise RuntimeError(f"Fixture failed for {worker}, {script}: " +
                               (result.stdout + result.stderr)[-1800:])


def build_workers():
    result = command(["make", "-j2", *WORKERS], check=False)
    if result.returncode:
        raise RuntimeError("Build failed: " + (result.stdout + result.stderr)[-1600:])
    for name in WORKERS:
        test_worker(name)


def render_service(name, cpu_quota=150):
    template = (ROOT / "production/systemd/keypool-hunt.service.in").read_text()
    if template.count("@WORKER@") != 2:
        raise RuntimeError("Unexpected unit template marker count")
    if name not in WORKERS:
        raise RuntimeError("Worker not in approved list")
    if not 50 <= cpu_quota <= 200:
        raise RuntimeError("CPU quota must be 50–200% total Pi CPU")
    if template.count("@CPU_QUOTA@") != 1:
        raise RuntimeError("Unexpected CPU quota template marker count")
    service = (template.replace("@WORKER@", name)
               .replace("@CPU_QUOTA@", str(cpu_quota) + "%"))
    if ("CPUQuota=" + str(cpu_quota) + "%" not in service
            or "Restart=on-failure" not in service):
        raise RuntimeError("Mandatory service guards removed")
    return service


def atomic_install(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise RuntimeError(f"Unit symlink is forbidden: {path}")
    fd, temp = tempfile.mkstemp(prefix=".keypool-unit-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def install(selected, cpu_quota=150):
    commit = source_commit()
    assert_user_service_inactive()
    if not DB.is_file():
        raise RuntimeError("Existing production campaign DB missing; deployment never initializes DB")
    # Build/test before touching the installation.
    build_workers()
    manifest = {
        "source_commit": commit,
        "default_worker": selected,
        "approved_workers": {name: sha256(ROOT / name) for name in WORKERS},
        "controller_sha256": sha256(FILES["keypoold.py"]),
        "preflight_sha256": sha256(FILES["keypool_preflight.py"]),
        "health_sha256": sha256(FILES["keypool_health.py"]),
        "release_policy": "immutable binaries, manual activation only",
    }
    release_name = commit[:12] + "-" + manifest["approved_workers"][selected][:12]
    RELEASES.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = RELEASES / release_name
    if dest.exists():
        raise RuntimeError(f"Release already installed, refusing overwrite: {dest}")
    staging = Path(tempfile.mkdtemp(prefix=".keypool-stage-", dir=RELEASES))
    try:
        for name, src in FILES.items():
            shutil.copy2(src, staging / name)
            os.chmod(staging / name, 0o400)
        for name in WORKERS:
            shutil.copy2(ROOT / name, staging / name)
            os.chmod(staging / name, 0o500)
        (staging / "release-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.chmod(staging / "release-manifest.json", 0o400)

        # Test the EXACT copied immutable release, before switching current.
        preflight = staging / "keypool_preflight.py"
        r = subprocess.run([sys.executable, str(preflight),
                            "--db", str(DB), "--worker", selected],
                           capture_output=True, text=True, timeout=20)
        if r.returncode:
            raise RuntimeError("Candidate release preflight failed: " + r.stderr.strip())
        staging.rename(dest)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    # Recheck immediately before altering any pointer.
    assert_user_service_inactive()
    BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if CURRENT.exists() and not CURRENT.is_symlink():
        raise RuntimeError("Current path is not a symlink; refusal to overwrite")
    tmp_link = BASE / (".current-" + release_name)
    if tmp_link.exists() or tmp_link.is_symlink():
        raise RuntimeError("Stale current symlink candidate")
    tmp_link.symlink_to(dest, target_is_directory=True)
    os.replace(tmp_link, CURRENT)

    files = {
        "keypool-hunt.service": render_service(selected, cpu_quota),
        "keypool-health.service": (
            ROOT / "production/systemd/keypool-health.service").read_text(),
        "keypool-health.timer": (
            ROOT / "production/systemd/keypool-health.timer").read_text()
    }
    for name, data in files.items():
        atomic_install(UNITS / name, data)
    result = command(["systemctl", "--user", "daemon-reload"], check=False)
    if result.returncode:
        raise RuntimeError("Unit files installed but daemon-reload failed: " + result.stderr)

    print(json.dumps({
        "installed_release": str(dest), "selected_worker": selected,
        "cpu_quota_percent": cpu_quota,
        "worker_sha256": manifest["approved_workers"][selected],
        "commit": commit, "service_state": "NOT started or enabled",
        "target_db": str(DB)
    }, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker", choices=WORKERS, default=WORKERS[0])
    ap.add_argument("--cpu-quota", type=int, default=150, metavar="PERCENT",
                    help="Total CPU quota, 50..200 percent (default 150)")
    ap.add_argument("--validate-template", action="store_true",
                    help="Only validate unit template content, no host writes")
    args = ap.parse_args()
    try:
        if args.validate_template:
            for worker in WORKERS:
                unit = render_service(worker, args.cpu_quota)
                assert "ExecStartPre=" in unit and "--max-jobs 0" in unit
            print("PASS: three selectable workers; safe systemd template")
        else:
            install(args.worker, args.cpu_quota)
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print("Keypool deploy REFUSED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
