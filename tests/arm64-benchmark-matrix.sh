#!/usr/bin/env bash
# A/B/C experiment on a physical Pi 5. Exactly the same #71 workload
# for all variants. No continuous/background search or service changes.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
TARGET="${KEYHUNT_TARGET:-$ROOT/runs/bench71/target.txt}"
RUN="${KEYHUNT_RUN_DIR:-$ROOT/runs/arm64-su2-center-comparison}"
SECONDS_PER_RUN="${KEYHUNT_BENCH_SECONDS:-27}"

if [[ ! -f "$TARGET" ]]; then
  echo "Missing target: $TARGET (set KEYHUNT_TARGET)" >&2
  exit 2
fi
mkdir -p "$RUN"
printf 'Benchmark target: %s\nLogs: %s\n' "$TARGET" "$RUN"

for bin in keyhunt-arm64-sha2-neon \
           keyhunt-arm64-sha2-neon-su2 \
           keyhunt-arm64-sha2-neon-su2-center; do
  if [[ ! -x "$REPO/$bin" ]]; then
    echo "Missing $REPO/$bin; build the three variants first." >&2
    exit 2
  fi
done

printf '\n%-41s %7s %18s\n' 'Variant' 'Threads' 'Reported keys/s'
for t in 1 4; do
  for bin in keyhunt-arm64-sha2-neon \
             keyhunt-arm64-sha2-neon-su2 \
             keyhunt-arm64-sha2-neon-su2-center; do
    logfile="$RUN/${bin}-t${t}.log"
    rc=0
    timeout --foreground --signal=TERM --kill-after=5s \
      "${SECONDS_PER_RUN}s" nice -n 15 "$REPO/$bin" \
      -m address -f "$TARGET" -b 71 -l compress -R \
      -n 0x100000 -t "$t" -q -s 5 > "$logfile" 2>&1 || rc=$?
    # GNU timeout returns 124 for the intended bounded duration.
    if [[ "$rc" -ne 0 && "$rc" -ne 124 && "$rc" -ne 143 ]]; then
      echo "Unexpected exit code $rc from $bin t=$t" >&2
      tail -35 "$logfile" >&2
      exit "$rc"
    fi
    status="$(tr '\r' '\n' < "$logfile" | grep 'Total .* keys' | tail -1 || true)"
    if [[ -z "$status" ]]; then
      echo "Missing throughput result for $bin t=$t" >&2
      tail -35 "$logfile" >&2
      exit 1
    fi
    printf '%-41s %7s %s\n' "$bin" "$t" "$status"
  done
done

if command -v vcgencmd >/dev/null; then
  vcgencmd measure_temp
  vcgencmd get_throttled
fi
echo 'Note: in compressed-X dual-prefix mode, displayed keys/s includes'
echo 'both prefixes; actual candidate x-coordinate rate is ~half.'
