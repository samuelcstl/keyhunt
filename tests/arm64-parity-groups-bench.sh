#!/usr/bin/env bash
# Four variants, same random Puzzle #71 workload and runtime.
# Reports distinct scalar candidates/s, not dual-prefix hash attempts/s.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
RUN="${KEYHUNT_RUN_DIR:-$ROOT/runs/arm64-parity-groups-comparison}"
TARGET="${KEYHUNT_TARGET:-$ROOT/runs/bench71/target.txt}"
LIMIT="${KEYHUNT_BENCH_SECONDS:-27}"
mkdir -p "$RUN"
if [[ ! -f "$TARGET" ]]; then echo "Missing $TARGET" >&2; exit 2; fi

variants=(
  keyhunt-arm64-sha2-neon-su2-center
  keyhunt-arm64-sha2-neon-su2-center-parity
  keyhunt-arm64-sha2-neon-su2-center-512
  keyhunt-arm64-sha2-neon-su2-center-2048
)
for variant in "${variants[@]}"; do
  if [[ ! -x "$REPO/$variant" ]]; then echo "Missing build: $variant" >&2; exit 2; fi
done
printf '%-47s %4s %15s %15s\n' Variant CPUs Reported_keys/s Distinct_keys/s
for threads in 1 4; do
  for variant in "${variants[@]}"; do
    output="$RUN/$variant-t$threads.log"
    code=0
    timeout --foreground --signal=TERM --kill-after=5s "${LIMIT}s" \
      nice -n 15 "$REPO/$variant" -m address -f "$TARGET" \
      -b 71 -l compress -R -n 0x100000 -t "$threads" -q -s 5 \
      > "$output" 2>&1 || code=$?
    if [[ $code -ne 0 && $code -ne 124 && $code -ne 143 ]]; then
      echo "Unexpected $variant exit=$code" >&2
      tail -40 "$output" >&2
      exit 1
    fi
    last="$(tr '\r' '\n' < "$output" | grep 'Total .* keys' | tail -1 || true)"
    if [[ -z "$last" ]]; then echo "Missing throughput for $variant" >&2; tail -40 "$output"; exit 1; fi
    if [[ "$last" =~ \(([0-9]+)[[:space:]]keys/s\) ]]; then
      reported="${BASH_REMATCH[1]}"
    elif [[ "$last" =~ :[[:space:]]([0-9]+)[[:space:]]keys/s ]]; then
      reported="${BASH_REMATCH[1]}"
    else
      echo "Unrecognized throughput: $last" >&2; exit 1
    fi
    if [[ "$variant" == *-parity ]]; then distinct="$reported"
    else distinct="$((reported / 2))"
    fi
    printf '%-47s %4d %15d %15d\n' "$variant" "$threads" "$reported" "$distinct"
  done
done
if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd measure_temp
  vcgencmd get_throttled
fi
echo "All binaries compare scalar key coverage; duplicates between randomly selected chunks are not deduplicated."
echo "Raw logs: $RUN"
