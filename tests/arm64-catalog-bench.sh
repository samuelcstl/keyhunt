#!/usr/bin/env bash
# Manual Pi5 catalog screening. Real Keypool SQLite and services untouched.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
MODE="${1:-all}"
case "$MODE" in all|workers|micro|pipelines) ;; *)
  echo "Usage: bash tests/arm64-catalog-bench.sh [all|workers|micro|pipelines]" >&2; exit 2 ;;
esac
[[ "$(uname -m)" == aarch64 ]] || { echo 'Pi5 AArch64 required' >&2; exit 2; }
[[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]] || {
  echo 'Refusing modified tracked sources' >&2; exit 2;
}
RUN="${KEYHUNT_CATALOG_RUN_DIR:-$ROOT/../runs/arm64-catalog/$(date -u +%Y%m%dT%H%M%SZ)-$$-$MODE}"
[[ ! -e "$RUN" ]] || { echo "Refusing to overwrite $RUN" >&2; exit 2; }
mkdir -p "$RUN/sources"
chmod 700 "$RUN"
source "$ROOT/tests/arm64-evidence-archive.sh"
archive_catalog() {
  local rc=$?
  trap - EXIT
  if find "$RUN" -type f -name 'FOUND.private' -print -quit | grep -q .; then
    echo 'PRIVATE KEY HIT: suppressing remote archive; keep evidence local.' >&2
    exit "$rc"
  fi
  kh_archive_on_exit "$rc" "$RUN" arm64-catalog
}
trap archive_catalog EXIT
{
  date -u +%FT%TZ
  git -C "$ROOT" rev-parse HEAD
  git -C "$ROOT" branch --show-current
  uname -a
  g++ --version | head -1
  echo "mode=$MODE; build_budget=${KEYHUNT_CATALOG_BUILD_LIMIT:-420}s; bench_budget=${KEYHUNT_CATALOG_BENCH_LIMIT:-420}s"
  echo "Never launches production campaign or writes its SQLite"
} > "$RUN/provenance.txt"
for p in Makefile keyhunt.cpp config/keyhunt-arm64-catalog.json \
  tests/arm64-catalog-bench.py tests/arm64-catalog-bench.sh \
  tests/keypool-performance-ab.py; do
  mkdir -p "$RUN/sources/$(dirname "$p")"
  cp "$ROOT/$p" "$RUN/sources/$p"
done
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -35 > "$RUN/process-before.txt" || true
if command -v vcgencmd >/dev/null; then
  { vcgencmd measure_temp; vcgencmd measure_clock arm; vcgencmd get_throttled; } > "$RUN/sensors-before.txt"
fi
# Hard build cap. No production binary switched.
timeout --signal=TERM --kill-after=15s "${KEYHUNT_CATALOG_BUILD_LIMIT:-420}s" \
  make -C "$ROOT" -j2 arm64-catalog-build 2>&1 | tee "$RUN/build.log"
# Essential smoke: Puzzle20 coverage/replay and standalone pipeline checks.
timeout --signal=TERM --kill-after=15s 180s \
  make -C "$ROOT" -j2 arm64-r7-unprofiled-variants-test \
    arm64-pipelines-unprofiled-test 2>&1 | tee "$RUN/correctness.log"
python3 "$ROOT/tests/arm64-catalog-bench.py" --selftest | tee "$RUN/catalog-check.log"
cd "$ROOT"
python3 "$ROOT/tests/arm64-catalog-bench.py" \
  --mode "$MODE" --jobs "${KEYHUNT_CATALOG_JOBS:-64}" \
  --repeats "${KEYHUNT_CATALOG_REPEATS:-2}" \
  --seconds "${KEYHUNT_CATALOG_SECONDS:-2}" \
  --max-seconds "${KEYHUNT_CATALOG_BENCH_LIMIT:-420}" \
  --run-dir "$RUN/screen" 2>&1 | tee "$RUN/screen.log"
if command -v vcgencmd >/dev/null; then
  { vcgencmd measure_temp; vcgencmd measure_clock arm; vcgencmd get_throttled; } > "$RUN/sensors-after.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -35 > "$RUN/process-after.txt" || true
echo "Catalog report: $RUN/screen/summary.txt"
echo "Autopacked evidence archive will be written to $HOME."
