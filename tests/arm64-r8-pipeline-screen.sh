#!/usr/bin/env bash
# Physical Pi: independent 60s ECC width tests with real HASH160 consumer.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R8_PIPE_RUN_DIR:-$REPO/../runs/arm64-r8-pipeline/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
SEC="${KEYHUNT_R8_PIPE_SECONDS:-60}"
REPEATS="${KEYHUNT_R8_PIPE_REPEATS:-1}"
QUEUE="${KEYHUNT_R8_PIPE_QUEUE:-32}"
[[ ! -e "$RUN" ]] || exit 2
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || { echo "Tracked files are dirty" >&2; exit 2; }
mkdir -p "$RUN"/{codegen,measurements}
source "$REPO/tests/arm64-evidence-archive.sh"
trap 'kh_archive_on_exit "$?" "$RUN" r8-pipeline' EXIT
{
  git -C "$REPO" rev-parse HEAD
  uname -a
  g++ --version | head -1
  echo "seconds=$SEC repeats=$REPEATS queue=$QUEUE"
} > "$RUN/provenance.txt"
for f in Makefile tests/arm64-r8-ecc-hash-pipeline.cpp secp256k1/IntGroup.cpp secp256k1/field_k1_arm64.cpp hash/hash4_arm_sha2_su2.cpp hash/ripemd160_neon4.cpp; do
  mkdir -p "$RUN/codegen/$(dirname "$f")"
  cp "$REPO/$f" "$RUN/codegen/$f"
done
if command -v vcgencmd >/dev/null; then
 { vcgencmd get_throttled; vcgencmd measure_clock arm; vcgencmd measure_temp; } > "$RUN/before.txt"
fi
ps -eo pid,comm,%cpu --sort=-%cpu | head -25 > "$RUN/processes-before.txt" || true
make -C "$REPO" -j4 arm64-r8-pipeline 2>&1 | tee "$RUN/build.log"
make -C "$REPO" arm64-r8-pipeline-test 2>&1 | tee "$RUN/correctness.log"
cp "$REPO/build/arm64/r8-ecc-hash-pipeline" "$RUN/codegen/benchmark.bin"
sha256sum "$RUN/codegen/benchmark.bin" > "$RUN/codegen/binary.sha256"
objdump -drwC "$REPO/build/arm64/r8-ecc-hash-pipeline" > "$RUN/codegen/disassembly.txt"
echo "repeat,width,queue,mode,elapsed_s,produced_keys,hashed_keys,hashed_Mkeys_s,producer_inverse_ms,producer_points_ms,consumer_hash_ms,queue_full_ms,queue_empty_ms,peak_packets,hits" > "$RUN/measurements/results.csv"
for ((rep=1;rep<=REPEATS;rep++)); do
  if (( rep % 2 == 1 )); then widths=(1 2 4 8 16); else widths=(16 8 4 2 1); fi
  for width in "${widths[@]}"; do
    name="r${rep}-w${width}"
    "$REPO/build/arm64/r8-ecc-hash-pipeline" --width "$width" --queue "$QUEUE" --seconds "$SEC" > "$RUN/measurements/$name.csv" 2> "$RUN/measurements/$name.err"
    tail -n1 "$RUN/measurements/$name.csv" | sed "s/^/$rep,/" >> "$RUN/measurements/results.csv"
    echo "Completed $name"
    tail -n1 "$RUN/measurements/$name.csv"
    if command -v vcgencmd >/dev/null; then
      { vcgencmd get_throttled; vcgencmd measure_clock arm; vcgencmd measure_temp; } > "$RUN/measurements/$name.sensor"
    fi
  done
done
if command -v vcgencmd >/dev/null; then
 { vcgencmd get_throttled; vcgencmd measure_clock arm; vcgencmd measure_temp; } > "$RUN/after.txt"
fi
ps -eo pid,comm,%cpu --sort=-%cpu | head -25 > "$RUN/processes-after.txt" || true
python3 "$REPO/tests/arm64-r8-pipeline-assess.py" "$RUN/measurements/results.csv" | tee "$RUN/assessment.txt"
