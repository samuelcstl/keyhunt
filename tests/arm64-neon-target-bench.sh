#!/usr/bin/env bash
# Compare complete parity-correct HASH160 output vs exact NEON target check.
# Every candidate still performs full SHA256 + RIPEMD160 compression.
# Repeat in alternating order to distinguish a real gain from heat/clocks.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
RUN_ROOT="${KEYHUNT_RUN_DIR:-$ROOT/runs/arm64-neon-target-ab}"
DIR="$RUN_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-${BASHPID}"
TARGET="${KEYHUNT_TARGET:-$ROOT/runs/bench71/target.txt}"
DURATION="${KEYHUNT_BENCH_SECONDS:-120}"
REPEATS="${KEYHUNT_BENCH_REPEATS:-1}"
MODE="${KEYHUNT_BENCH_MODE:-both}"       # both | control | neon
CHUNK="${KEYHUNT_BENCH_CHUNK:-0x100000}"
PUZZLE="${KEYHUNT_BENCH_PUZZLE:-71}"
PERF="${KEYHUNT_BENCH_PERF:-1}"        # 1 hardware counters; 0 throughput-only
read -r -a THREADS <<< "${KEYHUNT_BENCH_THREADS:-4}"
BASE=keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1
NEON=keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1-neon
[[ "$DURATION" =~ ^[0-9]+$ ]] && ((DURATION>=10)) || { echo "Invalid DURATION" >&2; exit 2; }
[[ "$REPEATS" =~ ^[0-9]+$ ]] && ((REPEATS>=1)) || { echo "Invalid REPEATS" >&2; exit 2; }
[[ "$PERF" =~ ^[01]$ ]] || { echo "Invalid KEYHUNT_BENCH_PERF" >&2; exit 2; }
if [[ -n "${KEYHUNT_BENCH_BINARIES:-}" ]]; then
  # Target any future binary without changing the script or re-running history.
  read -r -a variants <<< "$KEYHUNT_BENCH_BINARIES"
  MODE=custom
else
  case "$MODE" in
    both) variants=("$BASE" "$NEON") ;;
    control) variants=("$BASE") ;;
    neon) variants=("$NEON") ;;
    *) echo "Invalid KEYHUNT_BENCH_MODE ($MODE)" >&2; exit 2 ;;
  esac
fi
(( ${#variants[@]} > 0 )) || { echo "No binaries selected" >&2; exit 2; }
[[ "$PUZZLE" =~ ^[0-9]+$ ]] || { echo "Invalid puzzle bit count" >&2; exit 2; }
[[ "$CHUNK" =~ ^(0x[0-9a-fA-F]+|[0-9]+)$ ]] || { echo "Invalid chunk size" >&2; exit 2; }
for threads in "${THREADS[@]}"; do
  [[ "$threads" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid thread count $threads" >&2; exit 2; }
done
[[ -f "$TARGET" ]] || { echo "Missing target $TARGET" >&2; exit 2; }
for bin in "${variants[@]}"; do
  [[ -x "$REPO/$bin" ]] || { echo "Missing $REPO/$bin. Build with make arm64-neon-target" >&2; exit 2; }
done
if ((PERF)); then command -v perf >/dev/null || { echo "Missing perf; use KEYHUNT_BENCH_PERF=0" >&2; exit 2; }; fi
mkdir -p "$DIR"
echo "Two-minute sustained run: seconds=$DURATION, threads=${THREADS[*]}, repeats=$REPEATS, mode=$MODE, perf=$PERF, puzzle=$PUZZLE, chunk=$CHUNK"
printf 'variant\tthreads\trun\tkeys_per_second\tfirst_half_rate\tsecond_half_rate\tcycles\tinstructions\tbranches\tbranch_misses\tapprox_keys_full_window\n' > "$DIR/results.tsv"
printf 'head=%s\nstarted_utc=%s\nseconds=%s\nthreads=%s\nrepeats=%s\nmode=%s\nperf=%s\ntarget=%s\npuzzle=%s\nchunk=%s\n' \
  "$(git -C "$REPO" rev-parse HEAD)" "$(date -u +%FT%TZ)" "$DURATION" "${THREADS[*]}" "$REPEATS" "$MODE" "$PERF" "$TARGET" "$PUZZLE" "$CHUNK" > "$DIR/config.txt"
sensor_stop=''
trap '[[ -z "$sensor_stop" ]] || touch "$sensor_stop"' EXIT
for threads in "${THREADS[@]}";do
    for ((rep=1; rep<=REPEATS; rep++));do
        if ((rep%2));then order=("${variants[@]}")
        else order=(); for ((i=${#variants[@]}-1;i>=0;i--));do order+=("${variants[i]}");done;fi
        for bin in "${order[@]}";do
            stem="$DIR/$bin-t$threads-r$rep"
            log="$stem.log"; stat="$stem.perf"; thermal="$stem.thermal.tsv"
            printf 'utc\ttemperature\tarm_frequency\tthrottled\n' > "$thermal"
            sensor_stop="$stem.monitor.done"
            (
              if command -v vcgencmd >/dev/null 2>&1; then
                while [[ ! -f "$sensor_stop" ]]; do
                  printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" \
                    "$(vcgencmd measure_temp 2>/dev/null || true)" \
                    "$(vcgencmd measure_clock arm 2>/dev/null || true)" \
                    "$(vcgencmd get_throttled 2>/dev/null || true)" >> "$thermal"
                  sleep 10
                done
              fi
            ) & monitor_pid=$!
            echo "Running $bin threads=$threads repetition=$rep for ${DURATION}s"
            args=(timeout --foreground --signal=TERM --kill-after=5s "${DURATION}s" \
              nice -n 15 "$REPO/$bin" -m address -f "$TARGET" \
              -b "$PUZZLE" -l compress -R -n "$CHUNK" -t "$threads" -q -s 5)
            rc=0
            if ((PERF)); then
              perf stat -x, -e cycles:u,instructions:u,branches:u,branch-misses:u \
                -o "$stat" -- "${args[@]}" > "$log" 2>&1 || rc=$?
            else
              "${args[@]}" > "$log" 2>&1 || rc=$?
            fi
            touch "$sensor_stop"
            wait "$monitor_pid" || true
            sensor_stop=''
            if [[ "$rc" -ne 0 && "$rc" -ne 124 && "$rc" -ne 143 ]];then
                echo "$bin failed with $rc" >&2; tail -40 "$log"; exit 1
            fi
            python3 - "$bin" "$threads" "$rep" "$log" "$stat" "$PERF" "$DURATION" "$DIR/results.tsv" <<'PYRUN'
import csv, re, statistics, sys
from pathlib import Path
name, threads, rep, log_path, stat_path, perf, duration, output = sys.argv[1:]
text=Path(log_path).read_text(errors='replace').replace("\r","\n")
samples=[tuple(map(int,x)) for x in re.findall(
    r'Total\s+(\d+)\s+keys in\s+(\d+)\s+seconds:.*?\((\d+)\s+keys/s\)',text)]
if not samples:
    raise SystemExit(f"Missing Keyhunt throughput in {log_path}: {text[-600:]}")
total, seconds, rate=samples[-1]
windows=[(b[1],(b[0]-a[0])/(b[1]-a[1]))
         for a,b in zip(samples,samples[1:]) if b[1]>a[1]]
first=[r for t,r in windows if t<=seconds/2]
second=[r for t,r in windows if t>seconds/2]
early=statistics.mean(first) if first else rate
late=statistics.mean(second) if second else rate
counts={}
if int(perf):
    for line in Path(stat_path).read_text(errors='replace').splitlines():
        cols=line.split(',')
        if len(cols)<3: continue
        event=cols[2].strip()
        if event in ('cycles:u','instructions:u','branches:u','branch-misses:u'):
            raw=cols[0].strip().replace(' ','')
            if not raw.isdigit():
                raise SystemExit(f"PMU counter unavailable: {event}={raw}; set KEYHUNT_BENCH_PERF=0")
            counts[event]=int(raw)
    if len(counts)!=4:
        raise SystemExit(f"PMU events missing in {stat_path}")
# Perf samples the complete run. Keyhunt's last snapshot stops at a 5s
# boundary, so extend its measured average to the requested full duration.
# Approximation only: startup/exit and the final partial window are unobserved.
est_keys=round(total*float(duration)/seconds)
with open(output,'a',newline='') as file:
    csv.writer(file,delimiter='\t').writerow([
        name, threads, rep, rate, round(early), round(late),
        *[counts.get(x,'') for x in (
            'cycles:u','instructions:u','branches:u','branch-misses:u')],
        est_keys])
print(f"rate={rate:,}/s early={early:,.0f}/s late={late:,.0f}/s "
      f"late-vs-early={(late/early-1)*100:+.2f}%")
if counts:
    cy=counts['cycles:u']; ins=counts['instructions:u']
    br=counts['branches:u']; mis=counts['branch-misses:u']
    print(f"approx cycles/key={cy/est_keys:,.1f} "
          f"insn/key={ins/est_keys:,.1f} IPC={ins/cy:.2f} "
          f"branch misses/1000 keys={1000*mis/est_keys:.1f} "
          f"branch miss rate={100*mis/br:.2f}%")
PYRUN
            if [[ -s "$thermal" ]]; then
              echo "Thermals (first and last 10s samples):"
              sed -n '2p;$p' "$thermal"
            fi
        done
    done
done
python3 - "$DIR/results.tsv" <<'PY'
import csv,statistics,sys
from collections import defaultdict
data=defaultdict(list)
with open(sys.argv[1],newline="") as f:
    for row in csv.DictReader(f,delimiter="\t"):
        data[(int(row["threads"]),row["variant"])].append(row)
print("\nMedian sustained actual candidate throughput for selected variants")
for (threads,name),group in sorted(data.items()):
    med=lambda k: statistics.median(float(x[k]) for x in group)
    early,late=med('first_half_rate'),med('second_half_rate')
    print(f"threads={threads} median={med('keys_per_second'):,.0f}/s "
          f"late-vs-early={(late/early-1)*100:+.2f}% "
          f"{name}")
    if all(x['cycles'] for x in group):
        cy,ins,br,mis,keys=(med(k) for k in ('cycles','instructions','branches',
                                            'branch_misses','approx_keys_full_window'))
        print(f"  approximate cycles/key={cy/keys:,.1f}, insn/key={ins/keys:,.1f}, "
              f"IPC={ins/cy:.2f}, misses/1000 candidates={1000*mis/keys:.1f}, "
              f"branch-miss rate={100*mis/br:.2f}%")
for threads in sorted({k[0] for k in data}):
    bases=[v for (t,n),v in data.items() if t==threads and not n.endswith('-neon')]
    neons=[v for (t,n),v in data.items() if t==threads and n.endswith('-neon')]
    if bases and neons:
        a=statistics.median(int(x['keys_per_second']) for x in bases[0])
        b=statistics.median(int(x['keys_per_second']) for x in neons[0])
        print(f"threads={threads}: NEON vs control={(b/a-1)*100:+.2f}%")
print("PMU per-candidate counts are approximate: partial reporting window/startup.")
print("CPU cycles per candidate and Joules per candidate are different metrics.")
PY
if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd measure_temp
    vcgencmd get_throttled
fi
echo "Logs and saved counters: $DIR"
