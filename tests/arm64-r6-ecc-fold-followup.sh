#!/usr/bin/env bash
# Follow-up R6: only R3-SCHED vs R6-PAIR+FOLD, short direct real-worker A/B.
# Reuses already proven crypto vectors, avoids rebuilding unaffected binaries.
# Complete archive on success or failure, no production campaign.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R6_FOLD_RUN_DIR:-$REPO/../runs/arm64-r6-fold-followup/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
JOBS="${KEYHUNT_R6_FOLD_JOBS:-64}"
REPEATS="${KEYHUNT_R6_FOLD_REPEATS:-4}"
[[ ! -e "$RUN" ]] || { echo "Run directory already exists: $RUN" >&2; exit 2; }
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || {
  echo "Refusing to benchmark dirty tracked files" >&2; exit 2;
}
mkdir -p "$RUN"/{worker,codegen/binaries}
chmod 700 "$RUN"
source "$REPO/tests/arm64-evidence-archive.sh"
trap 'kh_archive_on_exit "$?" "$RUN" r6-fold-followup' EXIT
{
  date -u +%FT%TZ
  git -C "$REPO" rev-parse HEAD
  git -C "$REPO" branch --show-current
  uname -a
  g++ --version | head -1
  echo "mode=real-worker JSON protocol, scratch synthetic disjoint chunks"
  echo "jobs_per_observation=$JOBS repeats=$REPEATS"
  echo "control=keyhunt-worker-r3-ecc-sched"
  echo "candidate=keyhunt-worker-r6-ecc-fold"
} > "$RUN/provenance.txt"
for src in keyhunt.cpp Makefile secp256k1/field_k1_pair_ilp.cpp \
  secp256k1/field_k1_arm64.cpp; do
  mkdir -p "$RUN/codegen/sources/$(dirname "$src")"
  cp "$REPO/$src" "$RUN/codegen/sources/$src"
done
if command -v vcgencmd >/dev/null; then
  { vcgencmd get_throttled; vcgencmd measure_clock arm; vcgencmd measure_temp; } > "$RUN/host-before.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -30 > "$RUN/process-before.txt" || true
make -C "$REPO" -j2 keyhunt-worker-r3-ecc-sched \
  keyhunt-worker-r6-ecc-fold build/arm64/ecc-r6-pair-oracle \
  2>&1 | tee "$RUN/build.log"
"$REPO/build/arm64/ecc-r6-pair-oracle" 2>&1 | tee "$RUN/mul-oracle.log"
for bin in keyhunt-worker-r3-ecc-sched keyhunt-worker-r6-ecc-fold; do
  cp "$REPO/$bin" "$RUN/codegen/binaries/$bin"
  sha256sum "$REPO/$bin" >> "$RUN/codegen/binaries.sha256"
  objdump -drwC "$REPO/$bin" > "$RUN/codegen/$bin.disasm"
done
python3 "$REPO/tests/arm64-r1-worker-ab.py" \
  --control keyhunt-worker-r3-ecc-sched \
  --candidate keyhunt-worker-r6-ecc-fold \
  --jobs "$JOBS" --repeats "$REPEATS" \
  --run-dir "$RUN/worker/paired" 2>&1 | tee "$RUN/worker-summary.log"
if command -v vcgencmd >/dev/null; then
  { vcgencmd get_throttled; vcgencmd measure_clock arm; vcgencmd measure_temp; } > "$RUN/host-after.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -30 > "$RUN/process-after.txt" || true
echo "Short R6 fold-only A/B completed: $RUN"
echo "Archive will be created automatically by the EXIT handler."
