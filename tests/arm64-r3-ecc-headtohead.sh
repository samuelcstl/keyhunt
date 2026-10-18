#!/usr/bin/env bash
# Focused physical Pi5 direct A/B: R3 scalar scheduling versus R3 NEON.
# Both variants share identical R1/R2 ECC/hash objects except the ECC numerator.
# Runs synthetic scratch worker jobs, never the live Puzzle #71 SQLite campaign.
# Every exit, including failure, automatically creates a verified tar.gz.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R3_H2H_DIR:-$REPO/../runs/arm64-r3-ecc-h2h/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
[[ ! -e "$RUN" ]] || { echo "Evidence directory exists: $RUN" >&2; exit 2; }
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || {
  echo "Refusing dirty tracked source" >&2; exit 2;
}
mkdir -p "$RUN"/{worker,codegen/binaries}
chmod 700 "$RUN"
source "$REPO/tests/arm64-evidence-archive.sh"
trap 'kh_archive_on_exit "$?" "$RUN" r3-ecc-h2h' EXIT
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
ps -eo pid,ppid,stat,comm,%cpu,%mem --sort=-%cpu | head -40 > "$RUN/process-before.txt" || true
make -C "$REPO" -j4 arm64-r3-ecc 2>&1 | tee "$RUN/build.log"
for bin in keyhunt-worker-r3-ecc-sched keyhunt-worker-r3-ecc-neon; do
  cp "$REPO/$bin" "$RUN/codegen/binaries/$bin"
  sha256sum "$REPO/$bin" >> "$RUN/codegen/binaries.sha256"
done
python3 "$REPO/tests/arm64-r1-worker-ab.py" \
  --control keyhunt-worker-r3-ecc-sched \
  --candidate keyhunt-worker-r3-ecc-neon \
  --jobs "${KEYHUNT_R3_H2H_JOBS:-256}" \
  --repeats "${KEYHUNT_R3_H2H_REPEATS:-8}" \
  --run-dir "$RUN/worker/paired" 2>&1 | tee "$RUN/worker-summary.log"
ps -eo pid,ppid,stat,comm,%cpu,%mem --sort=-%cpu | head -40 > "$RUN/process-after.txt" || true
echo "Head-to-head raw run: $RUN"
echo "The EXIT trap produces the tar.gz plus SHA256 in $HOME."
