#!/usr/bin/env bash
# Fast R4 screening. No production worker is modified.
# Preserve raw evidence and tarball even if correctness/benchmark fails.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R4_RUN_DIR:-$REPO/../runs/arm64-r4-ecc/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
SECONDS_PER_VARIANT="${KEYHUNT_R4_SECONDS:-2}"
REPEATS="${KEYHUNT_R4_REPEATS:-2}"
[[ ! -e "$RUN" ]] || { echo "Run exists: $RUN" >&2; exit 2; }
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || {
  echo "Tracked source is dirty. Refusing unrepeatable bench." >&2;exit 2;
}
mkdir -p "$RUN/codegen"
chmod 700 "$RUN"
source "$REPO/tests/arm64-evidence-archive.sh"
trap 'kh_archive_on_exit "$?" "$RUN" r4-ecc' EXIT
{
  echo "utc=$(date -u +%FT%TZ)"
  echo "head=$(git -C "$REPO" rev-parse HEAD)"
  echo "branch=$(git -C "$REPO" branch --show-current)"
  uname -a
  g++ --version | head -1
  grep '^ARM64_CXXFLAGS ' "$REPO/Makefile"
  echo "seconds=$SECONDS_PER_VARIANT repeats=$REPEATS"
} > "$RUN/provenance.txt"
cp "$REPO/tests/arm64-r4-ecc-radix-screen.cpp" "$RUN/codegen/source.cpp"
cp "$REPO/secp256k1/field_k1_arm64.cpp" "$RUN/codegen/native-control.cpp"
cp "$REPO/Makefile" "$RUN/codegen/Makefile"
if command -v vcgencmd >/dev/null; then
  { vcgencmd measure_temp; vcgencmd measure_clock arm; vcgencmd get_throttled; } > "$RUN/host-before.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -30 > "$RUN/process-before.txt" || true
make -C "$REPO" -j4 arm64-r4-ecc-build 2>&1 | tee "$RUN/build.log"
cp "$REPO/build/arm64/ecc-radix-screen" "$RUN/codegen/ecc-radix-screen.bin"
sha256sum "$RUN/codegen/ecc-radix-screen.bin" > "$RUN/codegen/binary.sha256"
objdump -drwC "$REPO/build/arm64/ecc-radix-screen" > "$RUN/codegen/disassembly.txt"
make -C "$REPO" arm64-r4-ecc-test 2>&1 | tee "$RUN/correctness.log"
"$REPO/build/arm64/ecc-radix-screen" \
  --seconds "$SECONDS_PER_VARIANT" --repeats "$REPEATS" \
  2>"$RUN/benchmark-stderr.log" | tee "$RUN/benchmark.csv"
if command -v vcgencmd >/dev/null; then
  { vcgencmd measure_temp; vcgencmd measure_clock arm; vcgencmd get_throttled; } > "$RUN/host-after.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -30 > "$RUN/process-after.txt" || true
python3 "$REPO/tests/arm64-r4-ecc-assess.py" "$RUN/benchmark.csv" \
  | tee "$RUN/assessment.txt"
echo "Screen completed: $RUN"
echo "Archive and SHA256 will be written to $HOME by the EXIT trap."
