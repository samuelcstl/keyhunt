#!/usr/bin/env bash
# Deeper Cortex-A76 diagnosis for a *chosen* end-to-end Keyhunt binary.
# Combines PMU work and hardware-rate counters with call stacks and an
# instruction-level annotation, rather than ranking raw symbol percentages.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
BIN="${KEYHUNT_PROFILE_BIN:-keyhunt-arm64-sha2-neon-su2-center-parity-field-mul-sqr}"
DIR="${KEYHUNT_PROFILE_DIR:-$ROOT/runs/profile71-deep}"
TARGET="${KEYHUNT_TARGET:-$ROOT/runs/bench71/target.txt}"
DURATION="${KEYHUNT_PROFILE_SECONDS:-27}"
mkdir -p "$DIR"
[[ -x "$REPO/$BIN" && -f "$TARGET" ]] || { echo "Missing binary or target" >&2; exit 2; }
command -v perf >/dev/null || { echo "perf not installed" >&2; exit 2; }

args=("$REPO/$BIN" -m address -f "$TARGET" -b 71 -l compress
      -R -n 0x100000 -t 1 -q -s 5)
echo "Deep profiling $BIN with one CPU worker for ${DURATION}s"
echo "Perf files: $DIR"

# Linux PMU events vary across kernel builds. When the hardware events are
# inaccessible, preserve diagnostic availability via software clock samples.
pmu_rc=0
perf stat -x, -e cycles:u,instructions:u,branches:u,branch-misses:u \
   -o "$DIR/pmu.txt" -- \
   timeout --signal=TERM --kill-after=5s "${DURATION}s" \
   nice -n 15 "${args[@]}" > "$DIR/pmu-run.log" 2>&1 || pmu_rc=$?
if [[ "$pmu_rc" -eq 0 || "$pmu_rc" -eq 124 || "$pmu_rc" -eq 143 ]]; then
  echo "Hardware PMU sample complete (bounded benchmark exit $pmu_rc)"
else
  echo "Hardware counters may be inaccessible; see $DIR/pmu.txt" >&2
fi

# Hardware-cycle samples when available, software CPU-clock otherwise.
event=cycles:u
record() {
  perf record -e "$event" -F 199 --call-graph dwarf,4096 \
    -o "$DIR/perf.data" -- \
    timeout --signal=TERM --kill-after=5s "${DURATION}s" \
    nice -n 15 "${args[@]}" > "$DIR/profile-run.log" 2>&1
}
rc=0
record || rc=$?
if [[ "$rc" -ne 0 && "$rc" -ne 124 && "$rc" -ne 143 ]]; then
  echo "cycles sampling unavailable, retrying cpu-clock:u" >&2
  event=cpu-clock:u
  rc=0
  record || rc=$?
fi
if [[ "$rc" -ne 0 && "$rc" -ne 124 && "$rc" -ne 143 ]]; then
  echo "Perf recording failed; check event access and $DIR/profile-run.log" >&2
  exit 1
fi

perf report -i "$DIR/perf.data" --stdio --no-children \
    --sort=dso,symbol --percent-limit=0.5 > "$DIR/symbols.txt"
perf report -i "$DIR/perf.data" --stdio --children \
    --sort=dso,symbol --percent-limit=1 > "$DIR/callgraph.txt"
perf annotate -i "$DIR/perf.data" --stdio \
    --symbol field_k1_arm64_mul > "$DIR/mul-assembly.txt" 2>&1 || true
perf annotate -i "$DIR/perf.data" --stdio \
    --symbol thread_process > "$DIR/thread-assembly.txt" 2>&1 || true

echo "=== PMU COUNTERS (cycles, instructions, branches) ==="
cat "$DIR/pmu.txt" 2>/dev/null || true
echo "=== EXCLUSIVE HOT SYMBOLS ==="
grep -E '^ *[0-9]+\.[0-9]+%' "$DIR/symbols.txt" | head -20 || true
echo "=== SEARCH THROUGHPUT UNDER PROFILING ==="
tr '\r' '\n' < "$DIR/profile-run.log" | grep 'Total .* keys' | tail -1 || true
echo "=== SAVED DIAGNOSTICS ==="
printf '%s\n' "$DIR/symbols.txt" "$DIR/callgraph.txt" \
  "$DIR/mul-assembly.txt" "$DIR/thread-assembly.txt" "$DIR/pmu.txt"
echo "Use unprofiled end-to-end benchmarks for winner selection;"
echo "PMU ratios and annotate identify actual instruction costs/stalls."
