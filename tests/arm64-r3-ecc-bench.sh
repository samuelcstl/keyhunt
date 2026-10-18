#!/usr/bin/env bash
# R3 ECC pipeline controlled A/B, manual physical Pi only.
# R2-SRI control, independent scalar ECC pairing, and NEON pair subtraction.
# The production Keypool and default worker binaries are never selected.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R3_RUN_DIR:-$REPO/../runs/arm64-r3-ecc/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
variants=(keyhunt-r2-ripemd-sri keyhunt-r3-ecc-sched keyhunt-r3-ecc-neon)
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || {
  echo "Refusing to benchmark tracked source modifications" >&2; exit 2;
}
[[ ! -e "$RUN" ]] || { echo "Evidence path exists: $RUN" >&2; exit 2; }
mkdir -p "$RUN"/{codegen,standalone,workers}
chmod 700 "$RUN"
{
  date -u +%FT%TZ
  git -C "$REPO" rev-parse HEAD
  git -C "$REPO" branch --show-current
  uname -a
  g++ --version | head -1
  grep '^ARM64_CXXFLAGS' "$REPO/Makefile"
  if command -v vcgencmd >/dev/null; then
    vcgencmd get_throttled
    vcgencmd measure_temp
    vcgencmd measure_clock arm
  fi
} > "$RUN/provenance.txt"
make -C "$REPO" -j4 arm64-r3-ecc 2>&1 | tee "$RUN/build.log"
make -C "$REPO" arm64-r3-ecc-test 2>&1 | tee "$RUN/correctness.log"
for binary in "${variants[@]}" \
  keyhunt-worker-r2-ripemd-sri keyhunt-worker-r3-ecc-sched keyhunt-worker-r3-ecc-neon; do
  sha256sum "$REPO/$binary" >> "$RUN/codegen/binaries.sha256"
  objdump -drwC "$REPO/$binary" > "$RUN/codegen/$binary.disasm"
done
# Existing stable full-chain 4-thread PMU harness and heated reversed ABBA sweeps.
KEYHUNT_BENCH_BINARIES="${variants[*]}" \
KEYHUNT_BENCH_THREADS="${KEYHUNT_R3_THREADS:-4}" \
KEYHUNT_BENCH_REPEATS="${KEYHUNT_R3_REPEATS:-2}" \
KEYHUNT_BENCH_SECONDS="${KEYHUNT_R3_SECONDS:-120}" \
KEYHUNT_BENCH_PERF="${KEYHUNT_R3_PERF:-1}" \
KEYHUNT_RUN_DIR="$RUN/standalone" \
  bash "$REPO/tests/arm64-neon-target-bench.sh" 2>&1 | tee "$RUN/standalone.log"
for suffix in sched neon; do
  python3 "$REPO/tests/arm64-r1-worker-ab.py" \
    --control keyhunt-worker-r2-ripemd-sri \
    --candidate "keyhunt-worker-r3-ecc-$suffix" \
    --jobs "${KEYHUNT_R3_WORKER_JOBS:-256}" \
    --repeats "${KEYHUNT_R3_WORKER_REPEATS:-3}" \
    --run-dir "$RUN/workers/$suffix" 2>&1 | tee "$RUN/worker-$suffix.log"
done
(
  cd "$RUN"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
  sha256sum -c SHA256SUMS >/dev/null
)
echo "ECC R3 evidence: $RUN"
echo "Compare completed worker keys/s and cycles/key. Lower instruction count alone is insufficient."
