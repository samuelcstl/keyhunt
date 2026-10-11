#!/usr/bin/env bash
# Side-by-side PMU cost/candidate: field row+square baseline vs validated
# point-algebra + one-target direct lookup champion. Two runs, reversed order.
#
# A sample-level perf hot-symbol report cannot tell us which operation is
# avoidable. Cycles/instructions per actually scanned scalar let us separate
# reduced work from clock or scheduling noise.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
DIR="${KEYHUNT_PMU_DIR:-$ROOT/runs/arm64-pmu-baseline-champion}"
TARGET="${KEYHUNT_TARGET:-$ROOT/runs/bench71/target.txt}"
DURATION="${KEYHUNT_PMU_SECONDS:-24}"
REPEATS="${KEYHUNT_PMU_REPEATS:-2}"
CONTROL=keyhunt-arm64-sha2-neon-su2-center-parity-field-mul-sqr
CHAMPION=keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1
EVENTS=cycles:u,instructions:u,branches:u,branch-misses:u
mkdir -p "$DIR"
for x in "$REPO/$CONTROL" "$REPO/$CHAMPION" "$TARGET"; do
  [[ -f "$x" ]] || { echo "Missing: $x" >&2; exit 2; }
done
command -v perf >/dev/null || { echo "perf is required" >&2; exit 2; }

if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd measure_temp
  vcgencmd get_throttled
fi
printf 'binary\tthreads\trepeat\ttotal_keys\treported_keys_s\tcycles\tinstructions\tbranches\tbranch_misses\n' > "$DIR/samples.tsv"

for threads in 1 4; do
  for ((rep=1; rep<=REPEATS; ++rep)); do
    if (( rep % 2 )); then order=("$CONTROL" "$CHAMPION")
    else order=("$CHAMPION" "$CONTROL")
    fi
    for bin in "${order[@]}"; do
      filename="$DIR/${bin}-t${threads}-r${rep}"
      rc=0
      perf stat -x, -e "$EVENTS" -o "${filename}.perf" -- \
        timeout --foreground --signal=TERM --kill-after=5s "${DURATION}s" \
        nice -n 15 "$REPO/$bin" -m address -f "$TARGET" \
        -b 71 -l compress -R -n 0x100000 -t "$threads" -q -s 5 \
        > "${filename}.log" 2>&1 || rc=$?
      if [[ "$rc" -ne 0 && "$rc" -ne 124 && "$rc" -ne 143 ]]; then
        echo "Perf stat failed with $rc; inspect ${filename}.perf" >&2
        exit 1
      fi
      python3 - "$bin" "$threads" "$rep" "${filename}.perf" "${filename}.log" "$DIR/samples.tsv" <<'PY'
import re,sys
from pathlib import Path
bin,threads,rep,stat,log,output=sys.argv[1:]
pmu={}
for line in Path(stat).read_text().splitlines():
    cols=line.split(",")
    if len(cols)<3:
        continue
    key=cols[2].strip()
    if key in ("cycles:u","instructions:u","branches:u","branch-misses:u"):
        raw=cols[0].strip().replace(" ","")
        if not raw.isdigit():
            raise SystemExit(f"Invalid/unavailable PMU event {key}: {raw}; see {stat}")
        pmu[key]=int(raw)
if len(pmu)!=4:
    raise SystemExit(f"Missing one of four PMU events in {stat}: {pmu}")
matches=re.findall(r"Total\s+(\d+)\s+keys in\s+(\d+)\s+seconds:.*?\((\d+)\s+keys/s\)",
                   Path(log).read_text().replace("\r","\n"))
if not matches:
    raise SystemExit(f"Could not find actual candidate rate in {log}")
keys,elapsed,rate=map(int,matches[-1])
with open(output,"a") as f:
    vals=[bin,threads,rep,keys,rate,pmu["cycles:u"],pmu["instructions:u"],
          pmu["branches:u"],pmu["branch-misses:u"]]
    f.write("\t".join(map(str,vals))+"\n")
print(f"{bin:62s} threads={threads} repeat={rep} "
      f"rate={rate:,} cycles/key={pmu['cycles:u']/keys:,.1f} "
      f"insn/key={pmu['instructions:u']/keys:,.1f}")
PY
    done
  done
done

python3 - "$DIR/samples.tsv" <<'PY'
import csv,statistics,sys
from collections import defaultdict
d=defaultdict(list)
with open(sys.argv[1],newline="") as f:
    for row in csv.DictReader(f,delimiter="\t"):
        row={k:(v if k=="binary" else int(v)) for k,v in row.items()}
        d[(row["threads"],row["binary"])].append(row)
print("\nMedian A/B hardware cost per candidate")
print("threads  variant             rate_keys/s    cycles/key    insn/key      IPC  branch_miss/key")
for (threads,bin),rows in sorted(d.items()):
    med=lambda f: statistics.median(f(r) for r in rows)
    print(f"{threads:>7}  {('champion' if bin.endswith('point-direct1') else 'control'):18s} "
          f"{med(lambda r:r['reported_keys_s']):>12,.0f} "
          f"{med(lambda r:r['cycles']/r['total_keys']):>13,.1f} "
          f"{med(lambda r:r['instructions']/r['total_keys']):>11,.1f} "
          f"{med(lambda r:r['instructions']/r['cycles']):>8.2f} "
          f"{med(lambda r:r['branch_misses']/r['total_keys']):>16.3f}")
print("\nNote: total_key denominator is Keyhunt's measured count after startup;")
print("perf counters include startup, so absolute cycles/key are slightly inflated.")
print("Comparative deltas at the same worker count are the useful measure.")
PY
if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd measure_temp
  vcgencmd get_throttled
fi
echo "Raw results: $DIR/samples.tsv"
