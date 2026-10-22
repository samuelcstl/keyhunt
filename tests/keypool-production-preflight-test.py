#!/usr/bin/env python3
"""Zero-network, zero-systemd integration tests of fail-closed Keypool release."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pool"))
import keypoold as pool


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(*args, env=None):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True,
                          text=True, check=False, env=env, timeout=20)


def main():
    with tempfile.TemporaryDirectory(prefix="keypool-prod-fixture-") as tmp:
        base = Path(tmp)
        root = base / "release"
        root.mkdir(mode=0o700)
        campaign = base / "campaign.sqlite3"
        target = base / "target.txt"
        target.write_text(pool.TARGET + "\n", encoding="ascii")
        pool.init(campaign, target)
        copied = {
            "keypoold.py": ROOT / "pool/keypoold.py",
            "keypool_preflight.py": ROOT / "production/keypool_preflight.py",
        }
        for dest, src in copied.items():
            shutil.copyfile(src, root / dest)
        binary = "keyhunt-worker-r7-ecc-fold-unprofiled"
        shutil.copyfile("/bin/true", root / binary)
        os.chmod(root / binary, 0o700)
        manifest = {
            "source_commit": "test-only",
            "approved_workers": {binary: digest(root / binary)},
            "controller_sha256": digest(root / "keypoold.py"),
            "preflight_sha256": digest(root / "keypool_preflight.py")
        }
        manifest_file = root / "release-manifest.json"
        manifest_file.write_text(json.dumps(manifest))
        original_stat = campaign.stat()
        good = invoke(root / "keypool_preflight.py", "--db", campaign,
                      "--worker", binary)
        assert good.returncode == 0, good.stderr
        assert '"completed_chunks": 0' in good.stdout
        assert "seed" not in good.stdout.lower()

        # A replaced executable must fail, not silently start.
        (root / binary).write_bytes(b"tampered program")
        bad_hash = invoke(root / "keypool_preflight.py", "--db", campaign,
                          "--worker", binary)
        assert bad_hash.returncode != 0
        # The original intact file hash is restored.
        shutil.copyfile("/bin/true", root / binary)
        os.chmod(root / binary, 0o700)

        with sqlite3.connect(campaign) as conn:
            conn.execute("UPDATE campaign SET found=1 WHERE id=1")
            conn.commit()
        found = invoke(root / "keypool_preflight.py", "--db", campaign,
                       "--worker", binary)
        assert found.returncode != 0 and "already completed" in found.stderr
        with sqlite3.connect(campaign) as conn:
            conn.execute("UPDATE campaign SET found=0 WHERE id=1")
            conn.commit()

        absent = invoke(root / "keypool_preflight.py", "--db",
                        base / "missing.sqlite3", "--worker", binary)
        assert absent.returncode != 0
        assert not (base / "missing.sqlite3").exists()

        env = os.environ.copy()
        env["HOME"] = str(base / "home")
        health = invoke(ROOT / "production/keypool_health.py", "--db", campaign,
                        "--write", env=env)
        assert health.returncode == 0, health.stderr
        health_file = base / "home/.local/state/keypool/health.json"
        report = json.loads(health_file.read_text())
        assert report["completed_chunks"] == 0 and report["found"] is False
        assert "seed" not in health_file.read_text().lower()
        assert "key" not in json.dumps(report).lower().replace("keys", "")
        # New 24/7 telemetry is best-effort: sensors may be absent on CI.
        spec = importlib.util.spec_from_file_location(
            "keypool_health_under_test", ROOT / "production/keypool_health.py")
        health_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(health_module)
        fake_temp = base / "fake_cpu_temp"
        fake_temp.write_text("55430", encoding="ascii")
        assert health_module.cpu_temperature_c(fake_temp) == 55.43
        fake_temp.write_text("not-a-sensor", encoding="ascii")
        assert health_module.cpu_temperature_c(fake_temp) is None
        with patch.object(health_module.subprocess, "run",
                          return_value=subprocess.CompletedProcess(
                              ["vcgencmd"], 0, "throttled=0x50005\n", "")):
            assert health_module.pi_throttle_flags() == "0x50005"
        with patch.object(health_module, "read_progress", return_value={
                "chunks": 101, "inflight": None, "reissued": 0, "found": 0}), \
             patch.object(health_module, "load_previous", return_value={
                "unix_time": 1000.0, "completed_chunks": 101,
                "active_state": "active", "last_progress_unix": 100.0}), \
             patch.object(health_module, "systemd_active", return_value="active"), \
             patch.object(health_module.time, "time", return_value=1300.0), \
             patch.object(health_module, "cpu_temperature_c", return_value=55.43), \
             patch.object(health_module, "pi_throttle_flags", return_value="0x50005"):
            monitored = health_module.snapshot(campaign)
            assert monitored["stall_suspected"]
            assert monitored["seconds_since_progress"] == 1200
            assert monitored["pi_throttling_now"]
            assert monitored["pi_throttling_seen"]
            assert monitored["cpu_temperature_c"] == 55.43

        check_template = invoke(ROOT / "production/install_keypool.py",
                                "--validate-template")
        assert check_template.returncode == 0, check_template.stderr
        assert campaign.is_file()
        print("PASS: SQLite read-only preflight, tamper stop, hit stop, missing DB stop, redacted monitor, unit template")


if __name__ == "__main__":
    main()
