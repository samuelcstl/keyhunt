#!/usr/bin/env bash
# Compare only ECC group size on the Y-parity SHA256SU0/SU1 + NEON backend.
# Each reported key represents exactly one private-key scalar candidate.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
RUN="${KEYHUNT_RUN_DIR:-$ROOT/runs/parity-ecc-groups}"
TARGET="${KEYHUNT_TARGET:-$ROOT/runs/bench71/target.txt}"
DURATION="${KEYHUNT_BENCH_SECONDS:-27}"
mkdir -p "$RUN"
[[ -f "$TARGET" ]] || { echo "Missing target: $TARGET" >&2; exit 2; }

variants=(
  keyhunt-arm64-sha2-neon-su2-center-parity-512
  keyhunt-arm64-sha2-neon-su2-center-parity
  keyhunt-arm64-sha2-neon-su2-center-parity-2048
)
for bin in "${variants[@]}"; do
  [[ -x "$REPO/$bin" ]] || { echo "Build missing: $bin" >&2; exit 2; }
done
printf 'A/B/C ECC group sweep: Pi5, 33-byte SHA2 + NEON RIPEMD160, true Y parity\n'
printf 'Search: Puzzle #71, random chunks; results are scanned candidates, not guaranteed unique across chunks\n'
printf '%-54s %7s %16s\n' Binary Threads Candidates_per_s

for threads in 1 4; do
  for bin in "${variants[@]}"; do
    logfile="$RUN/${bin}-t${threads}.log"
    rc=0
    timeout --foreground --signal=TERM --kill-after=5s "${DURATION}s" \
      nice -n 15 "$REPO/$bin" -m address -f "$TARGET" \
      -b 71 -l compress -R -n 0x100000 -t "$threads" -q -s 5 \
      > "$logfile" 2>&1 || rc=$?
    if [[ "$rc" -ne 0 && "$rc" -ne 124 && "$rc" -ne 143 ]]; then
      echo "Unexpected exit status $rc for $bin" >&2
      tail -35 "$logfile" >&2
      exit 1
    fi
    last="$(tr '\r' '\n' < "$logfile" | grep 'Total .* keys' | tail -1 || true)"
    if [[ "$last" =~ \(([0-9]+)[[:space:]]keys/s\) ]]; then
      rate="${BASH_REMATCH[1]}"
    elif [[ "$last" =~ :[[:space:]]([0-9]+)[[:space:]]keys/s ]]; then
      rate="${BASH_REMATCH[1]}"
    else
      echo "No recognized throughput for $bin: $last" >&2
      exit 1
    fi
    printf '%-54s %7d %16d\n' "$bin" "$threads" "$rate"
  done
done

if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd measure_temp
  vcgencmd get_throttled
fi
printf 'Logs: %s\n' "$RUN"
