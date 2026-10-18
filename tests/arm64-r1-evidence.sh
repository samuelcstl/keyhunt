#!/usr/bin/env bash
# Pi-only correctness -> codegen -> PMU -> wall-clock evidence for CPU R1.
# Never touches the existing persistent campaign or switches production binaries.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
RUN="${KEYHUNT_R1_RUN_DIR:-$ROOT/runs/arm64-r1/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
BASE=keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1-neon
variants=("$BASE" keyhunt-r1-stride4 keyhunt-r1-neg-y keyhunt-r1-zero-mask keyhunt-r1-all)
if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]]; then
  echo "ERROR: tracked source is dirty; evidence requires an exact commit" >&2
  exit 2
fi
[[ ! -e "$RUN" ]] || { echo "Evidence path already exists: $RUN" >&2; exit 2; }
command -v objdump >/dev/null || { echo "objdump required" >&2; exit 2; }
command -v sha256sum >/dev/null || { echo "sha256sum required" >&2; exit 2; }
mkdir -p "$RUN/codegen" "$RUN/standalone" "$RUN/worker"
chmod 700 "$RUN"

# Capture build semantics from the *same* sources and flags as the binaries.
{
  echo "utc=$(date -u +%FT%TZ)"
  echo "head=$(git -C "$REPO" rev-parse HEAD)"
  echo "branch=$(git -C "$REPO" branch --show-current)"
  echo "kernel=$(uname -a)"
  echo "build=$(grep '^ARM64_CXXFLAGS ' "$REPO/Makefile")"
  echo "r1_defines=$(grep '^ARM64_R1_FLAGS ' "$REPO/Makefile")"
  echo "compiler=$(g++ --version | head -1)"
  echo "linker=$(ld --version | head -1)"
  echo "commands=make arm64-r1 (ordinary current flags; no profile-only rebuild)"
} > "$RUN/manifest.txt"
cp "$REPO/Makefile" "$RUN/codegen/Makefile.snapshot"
cp "$REPO/keyhunt.cpp" "$RUN/codegen/keyhunt.cpp.snapshot"
if [[ -r /proc/cpuinfo ]]; then cp /proc/cpuinfo "$RUN/cpuinfo.txt"; fi
ps -eo pid,ppid,stat,comm,%cpu,%mem --sort=-%cpu | head -40 > "$RUN/process-before.txt" || true
if command -v vcgencmd >/dev/null 2>&1; then
  { vcgencmd measure_temp; vcgencmd measure_clock arm; vcgencmd get_throttled; } > "$RUN/host-before.txt"
fi

make -C "$REPO" arm64-r1
if [[ "${KEYHUNT_R1_SKIP_TESTS:-0}" != 1 ]]; then
  make -C "$REPO" arm64-r1-test 2>&1 | tee "$RUN/correctness.log"
fi
for binary in "${variants[@]}" keyhunt-worker keyhunt-worker-r1; do
  sha256sum "$REPO/$binary" >> "$RUN/codegen/binaries.sha256"
  stat -c '%n %s bytes' "$REPO/$binary" >> "$RUN/codegen/sizes.txt"
  objdump -drwC "$REPO/$binary" > "$RUN/codegen/$binary.disasm"
  sha256sum "$RUN/codegen/$binary.disasm" >> "$RUN/codegen/disassembly.sha256"
done
g++ -Q -O3 -mcpu=cortex-a76 --help=optimizers > "$RUN/codegen/compiler-optimizers.txt" 2>&1 || true

# Existing A/B rig already captures repeated physical throughput, cycles,
# instructions, branch-misses and thermal samples in balanced reverse order.
# The PMU numbers per candidate are *approximate* due to 5s rate snapshots.
KEYHUNT_BENCH_BINARIES="${variants[*]}" \
KEYHUNT_BENCH_THREADS="${KEYHUNT_R1_THREADS:-4}" \
KEYHUNT_BENCH_REPEATS="${KEYHUNT_R1_REPEATS:-2}" \
KEYHUNT_BENCH_SECONDS="${KEYHUNT_R1_SECONDS:-120}" \
KEYHUNT_BENCH_PERF="${KEYHUNT_R1_PERF:-1}" \
KEYHUNT_RUN_DIR="$RUN/standalone" \
  bash "$REPO/tests/arm64-neon-target-bench.sh" 2>&1 | tee "$RUN/standalone-summary.log"

# Separate, actual worker path. This is not a second campaign and cannot
# advance the existing Keypool SQLite cursor. Full JSON pipeline and 4 threads.
python3 "$REPO/tests/arm64-r1-worker-ab.py" \
  --jobs "${KEYHUNT_R1_WORKER_JOBS:-256}" \
  --repeats "${KEYHUNT_R1_WORKER_REPEATS:-3}" \
  --run-dir "$RUN/worker/paired" 2>&1 | tee "$RUN/worker-summary.log"

# Instruction-level analysis after unprofiled selection, to avoid distorting it.
if [[ "${KEYHUNT_R1_PROFILE:-0}" == 1 ]]; then
  for binary in "$BASE" keyhunt-r1-all; do
    mkdir -p "$RUN/codegen/profile-$binary"
    KEYHUNT_PROFILE_BIN="$binary" \
    KEYHUNT_PROFILE_DIR="$RUN/codegen/profile-$binary" \
    KEYHUNT_PROFILE_SECONDS="${KEYHUNT_R1_PROFILE_SECONDS:-45}" \
      bash "$REPO/tests/arm64-deep-profile.sh" 2>&1 | tee "$RUN/codegen/profile-$binary.log"
  done
fi
if command -v vcgencmd >/dev/null 2>&1; then
  { vcgencmd measure_temp; vcgencmd measure_clock arm; vcgencmd get_throttled; } > "$RUN/host-after.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu,%mem --sort=-%cpu | head -40 > "$RUN/process-after.txt" || true
python3 "$REPO/tests/arm64-r1-assess.py" "$RUN" | tee "$RUN/assessment.log"
(
  cd "$RUN"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
  sha256sum -c SHA256SUMS >/dev/null
)
echo "Evidence at $RUN"
echo "Review codegen disassembly, real completed-worker keys/s, PMU cycles/key,"
echo "clocks, throttling and quality BEFORE accepting any optimization."
