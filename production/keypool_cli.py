#!/usr/bin/env python3
"""Keypool operator CLI: read-only status and explicit user-systemd control.

Commands:
    keypool             human-readable progress and health
    keypool health      same summary plus technical health details
    keypool logs        recent systemd logs
    keypool start       start service and enable boot autostart
    keypool stop        gracefully stop service and disable boot autostart
    keypool --json      original machine-readable campaign JSON
    keypool health --json  original health JSON
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

RELEASE = Path.home() / ".local/share/keypool/current"
SERVICE = "keypool-hunt.service"
CHUNK = 1 << 20
SIZE = 1 << 70


def command_json(file, *arguments):
    if not file.is_file():
        raise RuntimeError("Keypool release missing: " + str(file))
    proc = subprocess.run([sys.executable, str(file), *arguments], capture_output=True,
                          text=True, check=False, timeout=20)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip()
                           or "Keypool command failed")
    return json.loads(proc.stdout)


def service_control(action):
    """Change only the Keypool hunt service; never touch campaign SQLite.

    start enables persistence across reboot. stop prevents automatic restart.
    systemd's KillMode=mixed is responsible for graceful stop and checkpoint.
    """
    if action not in ("start", "stop"):
        raise ValueError("Unsupported Keypool service action")
    verb = "enable" if action == "start" else "disable"
    result = subprocess.run(
        ["systemctl", "--user", verb, "--now", SERVICE],
        capture_output=True, text=True, check=False, timeout=180,
    )
    if result.returncode:
        raise RuntimeError(
            (result.stderr or result.stdout).strip() or
            f"systemctl {verb} --now failed"
        )

    check = subprocess.run(
        ["systemctl", "--user", "show", SERVICE,
         "--property=ActiveState", "--value"],
        capture_output=True, text=True, check=False, timeout=15,
    )
    if check.returncode:
        raise RuntimeError(
            (check.stderr or check.stdout).strip() or
            "Cannot verify Keypool service state"
        )
    state = check.stdout.strip()
    expected = "active" if action == "start" else "inactive"
    if state != expected:
        raise RuntimeError(
            f"Unexpected Keypool state after {action}: {state or 'unknown'} "
            f"(expected {expected}); inspect 'keypool logs'"
        )
    print(
        "Keypool démarré. Démarrage automatique activé."
        if action == "start"
        else "Keypool arrêté. Démarrage automatique désactivé."
    )
    return 0


def fmt_float(number, places=2):
    return f"{number:,.{places}f}".replace(",", " ").replace(".", ",")


def fmt_count(number):
    number = int(number)
    if number >= 10 ** 15:
        exponent = len(str(number)) - 1
        return f"{fmt_float(number / 10 ** exponent, 3)} × 10^{exponent}"
    for factor, unit in ((10 ** 12, "billions"),
                         (10 ** 9, "milliards"),
                         (10 ** 6, "millions")):
        if number >= factor:
            value = fmt_float(number / factor, 2).rstrip("0").rstrip(",")
            return value + " " + unit
    return f"{number:,}".replace(",", " ")


def percent_text(keys, size):
    pct = keys * 100.0 / size
    if pct == 0:
        return "0 %"
    decimals = max(2, min(17, 2 - math.floor(math.log10(pct))))
    number = f"{pct:.{decimals}f}".rstrip("0").rstrip(".")
    return number.replace(".", ",") + " %"


def duration(seconds):
    if seconds is None or seconds < 0 or not math.isfinite(seconds):
        return "indisponible"
    if seconds >= 365.2425 * 86400:
        return "≈ " + fmt_float(seconds / (365.2425 * 86400), 1) + " ans"
    n = int(seconds // 60)
    days, n = divmod(n, 1440)
    hours, minutes = divmod(n, 60)
    if days:
        return f"≈ {days} j {hours} h"
    if hours:
        return f"≈ {hours} h {minutes:02d}"
    return f"≈ {minutes} min"


def next_milestone(keys):
    # A short, independently meaningful milestone, never mistaken for 100%
    # coverage. For 73 billion keys this is 100 billion; at 100 billion
    # the next milestone becomes one trillion.
    power = max(9, len(str(keys)))
    return 10 ** power


def progress_bar(fraction, width=24):
    filled = max(0, min(width, int(width * fraction)))
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def render_progress(status, health, verbose=False):
    keys = int(status["unique_completed_keys"])
    total_chunks = int(status["total_chunks"])
    size = total_chunks * CHUNK
    chunks = int(status["completed_chunks"])
    if size <= 0 or keys < 0 or keys > size:
        raise ValueError("invalid Keypool campaign coverage")
    active = health.get("active_state", "unknown")
    state = {"active": "EN COURS", "inactive": "ARRÊTÉ",
             "failed": "ÉCHEC", "activating": "DÉMARRAGE"}.get(
                 active, active.upper())
    rate = health.get("observed_mkeys_per_second")
    rate = float(rate) if rate is not None else None
    if rate is not None and (rate < 0 or not math.isfinite(rate)):
        rate = None
    goal = min(size, next_milestone(keys))
    milestone_fraction = keys / goal if goal else 1.0
    temp = health.get("cpu_temperature_c")
    throttled = health.get("pi_throttling_now")
    temperature = (fmt_float(float(temp), 1) + " °C") if temp is not None else "n/d"
    throttle = ("aucun" if throttled is False else
                "détecté" if throttled is True else "n/d")
    lines = [
        "KEYPOOL · PUZZLE #71",
        "Recherche       " + state,
        "Cible           " + str(status.get("target", "n/d")),
        "",
        "CLÉS EXPLORÉES  " + fmt_count(keys) + " / " + fmt_count(size),
        "Couverture      " + percent_text(keys, size) + " de l'intervalle",
        "Checkpoint      " + f"{chunks:,}".replace(",", " ") + " chunks validés",
        "",
        "PROCHAIN JALON  " + fmt_count(goal) + " de clés",
        progress_bar(milestone_fraction) + "  " +
        fmt_float(milestone_fraction * 100, 1) + " % du jalon",
    ]
    if rate is not None and rate > 0:
        keys_per_second = rate * 1e6
        lines += [
            "Temps estimé   " + duration((goal - keys) / keys_per_second),
            "",
            "DÉBIT           " + fmt_float(rate, 3) + " M clés/s",
            "Sur 24 heures  ≈ " + fmt_count(keys_per_second * 86400) + " / jour",
        ]
    else:
        lines += ["Temps estimé   en attente d'une mesure de débit",
                  "", "DÉBIT           en attente d'une mesure"]
    lines += [
        "Température     " + temperature + " · throttling : " + throttle,
        "Solution        " + ("TROUVÉE" if status.get("found") else "non trouvée"),
    ]
    if verbose:
        lines += [
            "",
            "DÉTAILS",
            "Chunk en cours " + ("oui" if status.get("inflight") is not None else "non"),
            "Reprises       " + str(status.get("recovery_restarts", 0)),
            "Blocage 15min  " + ("suspecté" if health.get("stall_suspected")
                                else "non détecté"),
            "Taux global    " + percent_text(keys, size) +
            " (ce n'est PAS le pourcentage du jalon)",
        ]
    lines += [
        "",
        "Le jalon est intermédiaire. La couverture totale reste minuscule.",
        "JSON brut : keypool --json | keypool health --json",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?",
                        choices=("status", "health", "logs", "start", "stop"),
                        default="status")
    parser.add_argument("--json", action="store_true",
                        help="Afficher le JSON original sans mise en forme")
    args = parser.parse_args()
    if args.command in ("start", "stop", "logs") and args.json:
        parser.error("--json est réservé à status et health")
    if args.command == "logs":
        return subprocess.call(["journalctl", "--user",
                                "-u", SERVICE, "-n", "40", "--no-pager"])
    try:
        if args.command in ("start", "stop"):
            return service_control(args.command)
        status = command_json(RELEASE / "keypoold.py", "status") if (
            not args.json or args.command == "status") else None
        health = command_json(RELEASE / "keypool_health.py") if (
            not args.json or args.command == "health") else None
        if args.json:
            value = status if args.command == "status" else health
            print(json.dumps(value, indent=2, ensure_ascii=False))
        else:
            print(render_progress(status, health, args.command == "health"))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError,
            json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print("keypool: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
