#!/usr/bin/env bash
# Measure the cost of avoidable work, not simply high-overhead symbols.
# Full end-to-end Puzzle 71; runs are interleaved in reverse order to
# reduce bias from thermal drift. 1 and 4 cores, default two repetitions.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
RUN="${KEYHUNT_RUN_DIR:-$ROOT/runs/arm64-avoid-work}"
TARGET="${KEYHUNT_TARGET:-$ROOT/runs/bench71/target.txt}"
DURATION="${KEYHUNT_BENCH_SECONDS:-22}"
REPEATS="${KEYHUNT_BENCH_REPEATS:-2}"
mkdir -p "$RUN"
[[ -f "$TARGET" ]] || { echo "Missing target $TARGET" >&2; exit 2; }

variants=(
  keyhunt-arm64-sha2-neon-su2-center-parity-field-mul-sqr
  keyhunt-arm64-sha2-neon-su2-center-parity-field-point
  keyhunt-arm64-sha2-neon-su2-center-parity-field-direct1
  keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1
)
for bin in "${variants[@]}"; do
  [[ -x "$REPO/$bin" ]] || { echo "Missing binary $bin" >&2; exit 2; }
done
data="$RUN/results.tsv"
printf 'binary\tthreads\trepetition\tkeys_per_second\n' > "$data"
if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd measure_temp
  vcgencmd get_throttled
fi
for threads in 1 4; do
  for ((round=1; round<=REPEATS; ++round)); do
    if (( round % 2 )); then ordered=("${variants[@]}")
    else ordered=("${variants[3]}" "${variants[2]}" "${variants[1]}" "${variants[0]}")
    fi
    for bin in "${ordered[@]}"; do
      logfile="$RUN/${bin}-t${threads}-r${round}.log"
      rc=0
      timeout --foreground --signal=TERM --kill-after=5s "${DURATION}s" \
        nice -n 15 "$REPO/$bin" -m address -f "$TARGET" \
        -b 71 -l compress -R -n 0x100000 -t "$threads" -q -s 5 \
        > "$logfile" 2>&1 || rc=$?
      if [[ "$rc" -ne 0 && "$rc" -ne 124 && "$rc" -ne 143 ]]; then
        echo "Unexpected status $rc from $bin" >&2
        tail -50 "$logfile" >&2
        exit 1
      fi
      last="$(tr '\r' '\n' < "$logfile" | grep 'Total .* keys' | tail -1 || true)"
      if [[ "$last" =~ \(([0-9]+)[[:space:]]keys/s\) ]]; then
        rate="${BASH_REMATCH[1]}"
      else
        echo "Cannot read rate $bin from: $last" >&2
        exit 1
      fi
      printf '%s\t%d\t%d\t%d\n' "$bin" "$threads" "$round" "$rate" >> "$data"
      printf '%-62s t=%d r=%d %d keys/s\n' "$bin" "$threads" "$round" "$rate"
    done
  done
done
python3 - "$data" <<'PY'
import csv,statistics,sys
from collections import defaultdict
records=defaultdict(list)
with open(sys.argv[1],newline='') as f:
    for r in csv.DictReader(f,delimiter='\t'):
        records[(int(r['threads']),r['binary'])].append(int(r['keys_per_second']))
print("\nMedians across repeated A/B/C/D measurements")
for key,vals in sorted(records.items()):
    print(f"threads={key[0]} median={statistics.median(vals):,.0f} "
          f"min={min(vals):,} max={max(vals):,}  {key[1]}")
PY
if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd measure_temp
  vcgencmd get_throttled
fi
echo "Rates count exact-parity scalar attempts, not unique deduplicated chunks."
echo "Results TSV and raw logs: $RUN"
