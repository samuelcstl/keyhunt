#!/usr/bin/env bash
# Focused matched A/B/C for RIPEMD160 NEON rotation on physical Raspberry Pi 5.
# Only build new objects; never overwrite the R1 control or production worker.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R2_RUN_DIR:-$REPO/../runs/arm64-r2-ripemd/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
variants=(keyhunt-r1-all keyhunt-r2-ripemd-sli keyhunt-r2-ripemd-sri)
[[ ! -e "$RUN" ]] || { echo "Output directory exists: $RUN" >&2; exit 2; }
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || {
  echo "Tracked source dirty; refused non-reproducible run" >&2; exit 2;
}
mkdir -p "$RUN/codegen" "$RUN/standalone" "$RUN/workers"
mkdir -p "$RUN/codegen/binaries" "$RUN/codegen/sources"
chmod 700 "$RUN"
# Generate a complete upload-ready tarball on normal exit AND on a test failure.
# Installed after RUN exists so early argument errors do not create misleading archives.
source "$REPO/tests/arm64-evidence-archive.sh"
trap 'kh_archive_on_exit "$?" "$RUN" r2-ripemd' EXIT
{
  date -u +%FT%TZ
  git -C "$REPO" rev-parse HEAD
  git -C "$REPO" branch --show-current
  uname -a
  g++ --version | head -1
  echo "compiler flags: $(grep '^ARM64_CXXFLAGS ' "$REPO/Makefile")"
} > "$RUN/provenance.txt"
cp "$REPO/Makefile" "$RUN/codegen/sources/Makefile"
cp "$REPO/keyhunt.cpp" "$RUN/codegen/sources/keyhunt.cpp"
cp "$REPO/hash/ripemd160_neon4.cpp" "$RUN/codegen/sources/"
make -C "$REPO" arm64-r2-ripemd-test 2>&1 | tee "$RUN/correctness.log"
for name in "${variants[@]}" keyhunt-worker-r1 keyhunt-worker-r2-ripemd-sli keyhunt-worker-r2-ripemd-sri; do
  sha256sum "$REPO/$name" >> "$RUN/codegen/binaries.sha256"
  cp "$REPO/$name" "$RUN/codegen/binaries/$name"
done
for name in "${variants[@]}"; do
  objdump -drwC "$REPO/$name" > "$RUN/codegen/$name.disasm"
done
python3 "$REPO/tests/arm64-r2-ripemd-asm.py" "${variants[@]}" \
  | tee "$RUN/codegen/rotation-opcodes.jsonlog"

# Sustained full scalar-to-HASH160 comparison, with hardware PMU if enabled.
KEYHUNT_BENCH_BINARIES="${variants[*]}" \
KEYHUNT_BENCH_THREADS="${KEYHUNT_R2_THREADS:-4}" \
KEYHUNT_BENCH_REPEATS="${KEYHUNT_R2_REPEATS:-2}" \
KEYHUNT_BENCH_SECONDS="${KEYHUNT_R2_SECONDS:-120}" \
KEYHUNT_BENCH_PERF="${KEYHUNT_R2_PERF:-1}" \
KEYHUNT_RUN_DIR="$RUN/standalone" \
  bash "$REPO/tests/arm64-neon-target-bench.sh" 2>&1 | tee "$RUN/standalone.log"

# Two isolated ABBA-style pairs, same temporary synthetic seed/chunks.
for suffix in sli sri; do
  python3 "$REPO/tests/arm64-r1-worker-ab.py" \
    --control keyhunt-worker-r1 \
    --candidate "keyhunt-worker-r2-ripemd-$suffix" \
    --jobs "${KEYHUNT_R2_WORKER_JOBS:-256}" \
    --repeats "${KEYHUNT_R2_WORKER_REPEATS:-3}" \
    --run-dir "$RUN/workers/$suffix" 2>&1 | tee "$RUN/worker-$suffix.log"
done

# SHA256SUMS and archive are finalized by the EXIT trap.
echo "Evidence directory: $RUN"
echo "Only promote if full-worker keys/s and PMU cycles/key both improve; verify clocks/thermals."
