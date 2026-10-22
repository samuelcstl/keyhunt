#!/usr/bin/env python3
"""Human-readable Keypool metrics: formatting, milestones and no false coverage."""
import importlib.util
from pathlib import Path

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


if __name__ == "__main__":
    main()
