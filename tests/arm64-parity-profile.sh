#!/usr/bin/env bash
# Sampling profile of the validated parity-aware Pi5 keyhunter.
# A single worker exposes true hashing/ECC hotspots without scheduler noise.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
BIN="${KEYHUNT_PROFILE_BIN:-keyhunt-arm64-sha2-neon-su2-center-parity}"
THREADS="${KEYHUNT_PROFILE_THREADS:-1}"
RUN="${KEYHUNT_PROFILE_DIR:-$ROOT/runs/profile71-su2-parity}"
SECONDS="${KEYHUNT_PROFILE_SECONDS:-32}"
TARGET="${KEYHUNT_TARGET:-$ROOT/runs/bench71/target.txt}"

command -v perf >/dev/null || { echo "perf is not installed" >&2; exit 2; }
[[ -x "$REPO/$BIN" ]] || { echo "Build missing: $BIN" >&2; exit 2; }
[[ -f "$TARGET" ]] || { echo "Target missing: $TARGET" >&2; exit 2; }
mkdir -p "$RUN"

echo "Profiling $BIN with $THREADS thread(s) for ${SECONDS}s"
echo "Output: $RUN"
rc=0
perf record -e cpu-clock:u -F 99 -o "$RUN/perf.data" \
  -- timeout --signal=TERM --kill-after=5s "${SECONDS}s" \
  nice -n 15 "$REPO/$BIN" \
    -m address -f "$TARGET" -b 71 -l compress -R \
    -n 0x100000 -t "$THREADS" -q -s 10 \
    > "$RUN/keyhunt.log" 2>&1 || rc=$?
if [[ "$rc" -ne 0 && "$rc" -ne 124 && "$rc" -ne 143 ]]; then
  echo "perf record returned unexpected status $rc" >&2
  tail -50 "$RUN/keyhunt.log" >&2
  exit 1
fi

perf report -i "$RUN/perf.data" --stdio --no-children \
  --sort=dso,symbol --percent-limit=0.5 \
  > "$RUN/report.txt"

echo "=== HOT SYMBOLS ==="
sed -n '1,90p' "$RUN/report.txt"

echo "=== PROFILED THROUGHPUT ==="
tr '\r' '\n' < "$RUN/keyhunt.log" | grep 'Total .* keys' | tail -1 || true

if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd measure_temp
  vcgencmd get_throttled
fi
echo "Upload or paste $RUN/report.txt; this sampling run is diagnostic,"
echo "not a substitute for an unprofiled throughput benchmark."
