#!/usr/bin/env bash
# One batch compares exact-parity SU2 + NEON search with two isolated
# ARM64 4x64 field implementations. All use 1024-point groups, same range,
# same SHA256SU0/SU1, RIPEMD160 and ECC point generator.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
RUN="${KEYHUNT_RUN_DIR:-$ROOT/runs/parity-arm64-field}"
TARGET="${KEYHUNT_TARGET:-$ROOT/runs/bench71/target.txt}"
DURATION="${KEYHUNT_BENCH_SECONDS:-27}"
mkdir -p "$RUN"
[[ -f "$TARGET" ]] || { echo "Missing target $TARGET" >&2; exit 2; }

variants=(
  keyhunt-arm64-sha2-neon-su2-center-parity
  keyhunt-arm64-sha2-neon-su2-center-parity-field-mul
  keyhunt-arm64-sha2-neon-su2-center-parity-field-mul-sqr
)
for bin in "${variants[@]}"; do
  [[ -x "$REPO/$bin" ]] || { echo "Build missing $bin" >&2; exit 2; }
done
printf 'Pi 5 parity field A/B/C: same 1024 group, same SHA256/RIPEMD search path\n'
printf '%-62s %4s %16s\n' Binary CPUs Candidates_per_s
for threads in 1 4; do
  for bin in "${variants[@]}"; do
    logfile="$RUN/${bin}-t${threads}.log"
    rc=0
    timeout --foreground --signal=TERM --kill-after=5s "${DURATION}s" \
      nice -n 15 "$REPO/$bin" -m address -f "$TARGET" \
      -b 71 -l compress -R -n 0x100000 -t "$threads" -q -s 5 \
      > "$logfile" 2>&1 || rc=$?
    if [[ "$rc" -ne 0 && "$rc" -ne 124 && "$rc" -ne 143 ]]; then
      echo "$bin failed unexpectedly with code $rc" >&2
      tail -40 "$logfile" >&2
      exit 1
    fi
    last="$(tr '\r' '\n' < "$logfile" | grep 'Total .* keys' | tail -1 || true)"
    if [[ "$last" =~ \(([0-9]+)[[:space:]]keys/s\) ]]; then
      rate="${BASH_REMATCH[1]}"
    else
      echo "No parseable rate for $bin: $last" >&2
      exit 1
    fi
    printf '%-62s %4d %16d\n' "$bin" "$threads" "$rate"
  done
done

if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd measure_temp
  vcgencmd get_throttled
fi
echo "Pi hashes one real compressed pubkey per scalar; keys/s is scalar attempts/s."
echo "Same as earlier: random chunk collisions across threads are not deduplicated."
echo "Logs: $RUN"
