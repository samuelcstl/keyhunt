#!/usr/bin/env bash
# R5 fast Pi screening: field-chain ILP vs resident NEON, not full Keyhunt.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R5_RUN_DIR:-$REPO/../runs/arm64-r5-ecc/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
SECONDS_PER_VARIANT="${KEYHUNT_R5_SECONDS:-1}"
REPEATS="${KEYHUNT_R5_REPEATS:-2}"
[[ ! -e "$RUN" ]] || { echo "Run exists: $RUN" >&2; exit 2; }
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || {
  echo "Tracked source is dirty; refusing nonreproducible benchmark." >&2; exit 2;
}
mkdir -p "$RUN/codegen"
chmod 700 "$RUN"
source "$REPO/tests/arm64-evidence-archive.sh"
trap 'kh_archive_on_exit "$?" "$RUN" r5-ecc' EXIT
{
  echo "utc=$(date -u +%FT%TZ)"
  echo "head=$(git -C "$REPO" rev-parse HEAD)"
  echo "branch=$(git -C "$REPO" branch --show-current)"
  uname -a
  g++ --version | head -1
  grep '^ARM64_CXXFLAGS ' "$REPO/Makefile"
  echo "seconds=$SECONDS_PER_VARIANT repeats=$REPEATS"
  echo "mode=two-independent-secp256k1-residues; chain=8-MUL-each"
} > "$RUN/provenance.txt"
cp "$REPO/tests/arm64-r5-ecc-chains.cpp" "$RUN/codegen/source.cpp"
cp "$REPO/secp256k1/field_k1_arm64.cpp" "$RUN/codegen/native-control.cpp"
cp "$REPO/Makefile" "$RUN/codegen/Makefile"
if command -v vcgencmd >/dev/null 2>&1; then
  { vcgencmd measure_temp;vcgencmd measure_clock arm;vcgencmd get_throttled; } > "$RUN/host-before.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -30 > "$RUN/process-before.txt" || true
make -C "$REPO" -j4 arm64-r5-ecc-build 2>&1 | tee "$RUN/build.log"
cp "$REPO/build/arm64/ecc-r5-chains" "$RUN/codegen/ecc-r5-chains.bin"
sha256sum "$RUN/codegen/ecc-r5-chains.bin" > "$RUN/codegen/binary.sha256"
objdump -drwC "$REPO/build/arm64/ecc-r5-chains" > "$RUN/codegen/disassembly.txt"
make -C "$REPO" arm64-r5-ecc-test 2>&1 | tee "$RUN/correctness.log"
"$REPO/build/arm64/ecc-r5-chains" \
  --seconds "$SECONDS_PER_VARIANT" --repeats "$REPEATS" \
  2>"$RUN/benchmark-stderr.log" | tee "$RUN/benchmark.csv"
if command -v vcgencmd >/dev/null 2>&1; then
  { vcgencmd measure_temp;vcgencmd measure_clock arm;vcgencmd get_throttled; } > "$RUN/host-after.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -30 > "$RUN/process-after.txt" || true
python3 "$REPO/tests/arm64-r5-ecc-assess.py" "$RUN/benchmark.csv" | tee "$RUN/assessment.txt"
echo "R5 raw evidence: $RUN"
echo "The EXIT trap will create $HOME/r5-ecc-results-*.tar.gz plus .sha256"
