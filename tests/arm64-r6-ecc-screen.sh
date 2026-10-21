#!/usr/bin/env bash
# R6 direct full-worker, scratch identical chunks: quick screening.
# R3-SCHED is immutable control. R6 pair/paired-fold source isolated.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R6_RUN_DIR:-$REPO/../runs/arm64-r6-ecc/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
[[ ! -e "$RUN" ]] || { echo "Run path exists: $RUN" >&2; exit 2; }
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || {
  echo "Refusing dirty tracked code" >&2; exit 2;
}
mkdir -p "$RUN"/{codegen/binaries,workers}
chmod 700 "$RUN"
source "$REPO/tests/arm64-evidence-archive.sh"
trap 'kh_archive_on_exit "$?" "$RUN" r6-ecc' EXIT
{
  date -u +%FT%TZ
  git -C "$REPO" rev-parse HEAD
  git -C "$REPO" branch --show-current
  uname -a
  g++ --version | head -1
  grep '^ARM64_CXXFLAGS ' "$REPO/Makefile"
  echo "jobs=${KEYHUNT_R6_JOBS:-32}"
  echo "repeats=${KEYHUNT_R6_REPEATS:-2}"
} > "$RUN/provenance.txt"
for file in Makefile keyhunt.cpp secp256k1/field_k1_pair_ilp.cpp \
  secp256k1/field_k1_arm64.cpp tests/arm64-r6-pair-oracle.cpp; do
  mkdir -p "$RUN/codegen/sources/$(dirname "$file")"
  cp "$REPO/$file" "$RUN/codegen/sources/$file"
done
if command -v vcgencmd >/dev/null; then
  { vcgencmd get_throttled; vcgencmd measure_clock arm; vcgencmd measure_temp; } > "$RUN/host-before.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -30 > "$RUN/process-before.txt" || true
make -C "$REPO" -j4 arm64-r6-ecc 2>&1 | tee "$RUN/build.log"
make -C "$REPO" arm64-r6-ecc-test 2>&1 | tee "$RUN/correctness.log"
for bin in keyhunt-worker-r3-ecc-sched \
  keyhunt-worker-r6-ecc-pair keyhunt-worker-r6-ecc-fold; do
  cp "$REPO/$bin" "$RUN/codegen/binaries/$bin"
  sha256sum "$REPO/$bin" >> "$RUN/codegen/binaries.sha256"
  objdump -drwC "$REPO/$bin" > "$RUN/codegen/$bin.disasm"
done
# Real four-core worker JSON protocol, identical synthetic temporary chunks.
# Each run has only 32*2^20 / ~7M ≈ 5s per treatment.
for candidate in pair fold; do
  python3 "$REPO/tests/arm64-r1-worker-ab.py" \
    --control keyhunt-worker-r3-ecc-sched \
    --candidate "keyhunt-worker-r6-ecc-$candidate" \
    --jobs "${KEYHUNT_R6_JOBS:-32}" \
    --repeats "${KEYHUNT_R6_REPEATS:-2}" \
    --run-dir "$RUN/workers/$candidate" 2>&1 | tee "$RUN/worker-$candidate.log"
done
if command -v vcgencmd >/dev/null; then
  { vcgencmd get_throttled; vcgencmd measure_clock arm; vcgencmd measure_temp; } > "$RUN/host-after.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -30 > "$RUN/process-after.txt" || true
echo "R6 evidence: $RUN"
echo "Automatic verified tar.gz written on exit even if the test fails."
