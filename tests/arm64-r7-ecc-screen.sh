#!/usr/bin/env bash
# R7: short real-worker ECC pipeline A/B and phase attribution.
# Uses private scratch jobs; no changes to existing Keypool/SQLite campaign.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R7_RUN_DIR:-$REPO/../runs/arm64-r7-ecc/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
JOBS="${KEYHUNT_R7_JOBS:-24}"
REPEATS="${KEYHUNT_R7_REPEATS:-2}"
[[ ! -e "$RUN" ]] || { echo "Run directory exists: $RUN" >&2; exit 2; }
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || {
  echo "Refusing dirty tracked source: benchmark would be unreproducible" >&2;exit 2;
}
mkdir -p "$RUN"/{codegen/binaries,codegen/sources,workers}
chmod 700 "$RUN"
source "$REPO/tests/arm64-evidence-archive.sh"
trap 'kh_archive_on_exit "$?" "$RUN" r7-ecc' EXIT
{
  date -u +%FT%TZ
  git -C "$REPO" rev-parse HEAD
  git -C "$REPO" branch --show-current
  uname -a
  g++ --version | head -1
  echo "jobs_per_observation=$JOBS"
  echo "repeats=$REPEATS"
  echo "stage_profile=on for R7 workers only"
} > "$RUN/provenance.txt"
for src in Makefile keyhunt.cpp secp256k1/field_k1_pair_ilp.cpp \
  secp256k1/field_k1_pair_ilp.h secp256k1/field_k1_arm64.cpp \
  tests/arm64-r7-pair-oracle.cpp tests/arm64-r7-stage-assess.py; do
  mkdir -p "$RUN/codegen/sources/$(dirname "$src")"
  cp "$REPO/$src" "$RUN/codegen/sources/$src"
done
if command -v vcgencmd >/dev/null;then
  { vcgencmd get_throttled;vcgencmd measure_clock arm;vcgencmd measure_temp; } > "$RUN/host-before.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -32 > "$RUN/process-before.txt" || true
make -C "$REPO" -j4 arm64-r7-ecc 2>&1 | tee "$RUN/build.log"
make -C "$REPO" arm64-r7-ecc-test 2>&1 | tee "$RUN/correctness.log"
for worker in keyhunt-worker-r3-ecc-sched \
  keyhunt-worker-r7-ecc-sched keyhunt-worker-r7-ecc-pair \
  keyhunt-worker-r7-ecc-fold;do
  cp "$REPO/$worker" "$RUN/codegen/binaries/$worker"
  sha256sum "$REPO/$worker" >> "$RUN/codegen/binaries.sha256"
  objdump -drwC "$REPO/$worker" > "$RUN/codegen/$worker.disasm"
done
for candidate in sched pair fold; do
  # Every variant sees identical key chunks. Each treatment has its own
  # fresh process and counter state; R3 is immutable external control.
  KEYHUNT_R7_STAGE_PROFILE=1 python3 "$REPO/tests/arm64-r1-worker-ab.py" \
    --control keyhunt-worker-r3-ecc-sched \
    --candidate "keyhunt-worker-r7-ecc-$candidate" \
    --jobs "$JOBS" --repeats "$REPEATS" \
    --run-dir "$RUN/workers/$candidate" 2>&1 | tee "$RUN/worker-$candidate.log"
done
python3 "$REPO/tests/arm64-r7-stage-assess.py" "$RUN/workers" \
  | tee "$RUN/stages.tsv"
if command -v vcgencmd >/dev/null;then
  { vcgencmd get_throttled;vcgencmd measure_clock arm;vcgencmd measure_temp; } > "$RUN/host-after.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -32 > "$RUN/process-after.txt" || true
echo "R7 evidence: $RUN"
echo "The automatic archive includes all untruncated logs, counters and SHA256."
