#!/usr/bin/env bash
# Compare complete parity-correct HASH160 output vs exact NEON target check.
# Every candidate still performs full SHA256 + RIPEMD160 compression.
# Repeat in alternating order to distinguish a real gain from heat/clocks.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
DIR="${KEYHUNT_RUN_DIR:-$ROOT/runs/arm64-neon-target-ab}"
TARGET="${KEYHUNT_TARGET:-$ROOT/runs/bench71/target.txt}"
DURATION="${KEYHUNT_BENCH_SECONDS:-24}"
REPEATS="${KEYHUNT_BENCH_REPEATS:-3}"
BASE=keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1
NEON=keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1-neon
mkdir -p "$DIR"
for x in "$REPO/$BASE" "$REPO/$NEON" "$TARGET";do
    [[ -f "$x" ]] || { echo "Missing $x" >&2; exit 2; }
done
printf 'variant\tthreads\trun\tkeys_per_second\n' > "$DIR/results.tsv"
for threads in 1 4;do
    for ((rep=1; rep<=REPEATS; rep++));do
        if ((rep%2));then order=("$BASE" "$NEON")
        else order=("$NEON" "$BASE");fi
        for bin in "${order[@]}";do
            log="$DIR/$bin-t$threads-r$rep.log"
            rc=0
            timeout --foreground --signal=TERM --kill-after=5s "${DURATION}s" \
              nice -n 15 "$REPO/$bin" -m address -f "$TARGET" \
              -b 71 -l compress -R -n 0x100000 -t "$threads" -q -s 5 \
              > "$log" 2>&1 || rc=$?
            if [[ "$rc" -ne 0 && "$rc" -ne 124 && "$rc" -ne 143 ]];then
                echo "$bin failed with $rc" >&2; tail -40 "$log"; exit 1
            fi
            line="$(tr '\r' '\n' < "$log" | grep 'Total .* keys' | tail -1 || true)"
            if [[ "$line" =~ \(([0-9]+)[[:space:]]keys/s\) ]];then
                rate="${BASH_REMATCH[1]}"
            else
                echo "Unparseable throughput: $line" >&2; exit 1
            fi
            printf '%s\t%d\t%d\t%d\n' "$bin" "$threads" "$rep" "$rate" >> "$DIR/results.tsv"
            printf 'threads=%d run=%d rate=%d candidate/s %s\n' "$threads" "$rep" "$rate" "$bin"
        done
    done
done
python3 - "$DIR/results.tsv" <<'PY'
import csv,statistics,sys
from collections import defaultdict
data=defaultdict(list)
with open(sys.argv[1],newline="") as f:
    for row in csv.DictReader(f,delimiter="\t"):
        data[(int(row["threads"]),row["variant"])].append(int(row["keys_per_second"]))
print("\nMedian actual scalar candidates/s")
for (threads,name),values in sorted(data.items()):
    print(f"threads={threads} median={statistics.median(values):,.0f} "
          f"range=[{min(values):,},{max(values):,}] "
          f"{'NEON target mask' if name.endswith('-neon') else 'full digest control'}")
for threads in (1,4):
    a=next(statistics.median(vals) for (t,name),vals in data.items()
           if t==threads and not name.endswith("-neon"))
    b=next(statistics.median(vals) for (t,name),vals in data.items()
           if t==threads and name.endswith("-neon"))
    print(f"threads={threads}: NEON vs control = {(b/a-1)*100:+.2f}%")
PY
if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd measure_temp
    vcgencmd get_throttled
fi
echo "Logs: $DIR"
