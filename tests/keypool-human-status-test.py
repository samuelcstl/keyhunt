#!/usr/bin/env python3
"""Human-readable Keypool metrics: formatting, milestones and no false coverage."""
import importlib.util
import contextlib
import io
import json
import subprocess
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "keypool_cli", ROOT / "production/keypool_cli.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def sample(keys, chunks=None):
    return {
        "target": "1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU",
        "completed_chunks": chunks if chunks is not None else keys // (1 << 20),
        "unique_completed_keys": str(keys),
        "total_chunks": 1 << 50,
        "percent": keys / (1 << 70) * 100,
        "inflight": chunks,
        "recovery_restarts": 1,
        "found": False,
    }


def main():
    chunks = 70008
    keys = chunks * (1 << 20)
    health = {
        "active_state": "active",
        "observed_mkeys_per_second": 2.905941,
        "cpu_temperature_c": 54.0,
        "pi_throttling_now": False,
        "stall_suspected": False
    }
    report = cli.render_progress(sample(keys, chunks), health)
    assert "73,41 milliards" in report, report
    assert "0,00000000622 %" in report, report
    assert "100 milliards" in report, report
    assert "73,4 %" in report, report
    assert "2,906 M clés/s" in report, report
    assert "251,07 milliards" in report, report
    assert "54,0 °C" in report, report
    assert "≈ 2 h 32" in report, report
    assert "EN COURS" in report and "TROUVÉE" not in report
    assert report.count("PROCHAIN JALON") == 1
    print("PASS: readable coverage and 100-billion milestone rate/ETA")

    empty = cli.render_progress(sample(0), {"active_state": "inactive",
                                            "observed_mkeys_per_second": None})
    assert "0 %" in empty and "ARRÊTÉ" in empty
    assert "en attente" in empty
    print("PASS: no invented rate or ETA before sampling")

    resumed = cli.render_progress(
        sample(10 ** 11, 95367),
        {"active_state": "active", "observed_mkeys_per_second": 3.0},
        verbose=True)
    assert "1 billion" in resumed, resumed
    assert "10,0 % du jalon" in resumed, resumed
    assert "Reprises       1" in resumed
    assert "Chunk en cours oui" in resumed
    print("PASS: milestones adjust upward, verbose recovery details")

    limit = 1 << 70
    complete = cli.render_progress(
        sample(limit, 1 << 50),
        {"active_state": "inactive", "observed_mkeys_per_second": 2.0})
    assert "100 %" in complete and "Taux global" not in complete
    assert "min" in complete
    print("PASS: 100% upper boundary without overflow")

    # Regression: render tests alone cannot detect omitted controller args.
    # Real CLI subprocess calls must invoke 'keypoold.py status', while the
    # separate health collector accepts no positional command.
    with tempfile.TemporaryDirectory(prefix="keypool-cli-contract-") as td:
        release = Path(td)
        status_json = json.dumps(sample(keys, chunks))
        health_json = json.dumps(health)
        (release / "keypoold.py").write_text(
            "import sys\n"
            "if sys.argv[1:] != ['status']: sys.exit(7)\n"
            f"print({status_json!r})\n",
            encoding="utf-8")
        (release / "keypool_health.py").write_text(
            "import sys\n"
            "if sys.argv[1:]: sys.exit(8)\n"
            f"print({health_json!r})\n",
            encoding="utf-8")
        with mock.patch.object(cli, "RELEASE", release):
            for args, expected in (
                (["keypool"], "KEYPOOL · PUZZLE #71"),
                (["keypool", "health"], "DÉTAILS"),
                (["keypool", "--json"], '"completed_chunks": 70008'),
                (["keypool", "health", "--json"], '"cpu_temperature_c": 54.0'),
            ):
                capture = io.StringIO()
                with mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(capture):
                    code = cli.main()
                assert code == 0, (args, capture.getvalue())
                assert expected in capture.getvalue(), (args, capture.getvalue())
    print("PASS: actual CLI calls include mandatory controller status subcommand")

    # CLI start/stop only call the fixed user-systemd unit, never campaign DB.
    for action, verb, expected_state, success_message in (
        ("start", "enable", "active", "Démarrage automatique activé"),
        ("stop", "disable", "inactive", "Démarrage automatique désactivé"),
    ):
        commands = []
        def pretend_systemctl(argv, **kwargs):
            commands.append((argv, kwargs))
            if argv == ["systemctl", "--user", verb, "--now", cli.SERVICE]:
                return subprocess.CompletedProcess(argv, 0, "", "")
            if argv == ["systemctl", "--user", "show", cli.SERVICE,
                        "--property=ActiveState", "--value"]:
                return subprocess.CompletedProcess(argv, 0, expected_state + "\n", "")
            raise AssertionError("unexpected command " + str(argv))

        with mock.patch.object(cli.subprocess, "run", side_effect=pretend_systemctl):
            with mock.patch.object(cli, "command_json", side_effect=AssertionError("must not read SQLite")):
                with mock.patch.object(sys, "argv", ["keypool", action]):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        assert cli.main() == 0, action
                    assert success_message in output.getvalue()
        assert len(commands) == 2
        assert commands[0][0] == ["systemctl", "--user", verb, "--now", cli.SERVICE]
        assert commands[0][1]["timeout"] >= 120
        assert commands[1][0] == [
            "systemctl", "--user", "show", cli.SERVICE,
            "--property=ActiveState", "--value",
        ]
    print("PASS: explicit start/stop use fixed systemd unit and verify final state")

    # Fail closed: no success message on systemctl error or mismatched state.
    for action, failure_mode in (
        ("start", "systemctl_error"),
        ("stop", "systemctl_error"),
        ("start", "unexpected_state"),
        ("stop", "unexpected_state"),
    ):
        result_calls = []
        def failed_systemctl(argv, **kwargs):
            result_calls.append(argv)
            if failure_mode == "systemctl_error":
                return subprocess.CompletedProcess(argv, 1, "", "permission denied")
            return subprocess.CompletedProcess(argv, 0, "inactive\n" if action == "start" else "active\n", "")
        with mock.patch.object(cli.subprocess, "run", side_effect=failed_systemctl):
            with mock.patch.object(sys, "argv", ["keypool", action]):
                err = io.StringIO()
                output = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(output):
                    assert cli.main() == 1
                assert "keypool:" in err.getvalue()
                assert "automatique activé" not in output.getvalue()
                assert "automatique désactivé" not in output.getvalue()
        assert len(result_calls) == (1 if failure_mode == "systemctl_error" else 2)
    print("PASS: failed start/stop never report success")

    for action in ("start", "stop", "logs"):
        with mock.patch.object(cli.subprocess, "run", side_effect=AssertionError("should not execute")):
            with mock.patch.object(sys, "argv", ["keypool", action, "--json"]):
                with contextlib.redirect_stderr(io.StringIO()):
                    try:
                        cli.main()
                    except SystemExit as exc:
                        assert exc.code == 2
                    else:
                        raise AssertionError("--json must be rejected")
    print("PASS: write-control commands reject JSON and do not expose secrets")


if __name__ == "__main__":
    main()
