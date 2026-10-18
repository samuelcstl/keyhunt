#!/usr/bin/env bash
# R9: same HASH160 consumer, compare ECC producer counts on physical Pi.
# Each sustained observation processes actual ECC points and HASH160 hits.
# Isolated binary; never touches Keypool DB or production worker.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R9_RUN_DIR:-$REPO/../runs/arm64-r9-pipeline/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
SEC="${KEYHUNT_R9_SECONDS:-60}"
REPEATS="${KEYHUNT_R9_REPEATS:-1}"
QUEUE="${KEYHUNT_R9_QUEUE:-32}"
[[ ! -e "$RUN" ]] || exit 2
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || { echo "Dirty tracked source" >&2; exit 2; }
mkdir -p "$RUN"/{codegen,measurements}
source "$REPO/tests/arm64-evidence-archive.sh"
trap 'kh_archive_on_exit "$?" "$RUN" r9-pipeline' EXIT
{
  git -C "$REPO" rev-parse HEAD
  uname -a
  g++ --version | head -1
  echo "seconds=$SEC repeats=$REPEATS queue=$QUEUE"
  echo "treatments=1p-w16,2p-w16,3p-w4,3p-w8,3p-w16"
  echo "hash_consumers=1, hashes 4 keys at a time, all producers share bounded queue"
} > "$RUN/provenance.txt"
for f in Makefile tests/arm64-r9-multi-pipeline.cpp secp256k1/IntGroup.cpp secp256k1/field_k1_arm64.cpp hash/hash4_arm_sha2_su2.cpp hash/ripemd160_neon4.cpp; do
  mkdir -p "$RUN/codegen/$(dirname "$f")"
  cp "$REPO/$f" "$RUN/codegen/$f"
done
if command -v vcgencmd >/dev/null; then
 { vcgencmd get_throttled; vcgencmd measure_clock arm; vcgencmd measure_temp; } > "$RUN/before.txt"
fi
ps -eo pid,comm,%cpu --sort=-%cpu | head -25 > "$RUN/processes-before.txt" || true
make -C "$REPO" -j4 arm64-r9-pipeline 2>&1 | tee "$RUN/build.log"
make -C "$REPO" arm64-r9-pipeline-test 2>&1 | tee "$RUN/correctness.log"
cp "$REPO/build/arm64/r9-multi-pipeline" "$RUN/codegen/benchmark.bin"
sha256sum "$RUN/codegen/benchmark.bin" > "$RUN/codegen/binary.sha256"
objdump -drwC "$REPO/build/arm64/r9-multi-pipeline" > "$RUN/codegen/disassembly.txt"
echo "repeat,producers,width,queue,mode,elapsed_s,produced_keys,hashed_keys,hashed_Mkeys_s,producer_inverse_ms,producer_points_ms,consumer_hash_ms,queue_full_ms,queue_empty_ms,peak_packets,hits" > "$RUN/measurements/results.csv"
for ((rep=1;rep<=REPEATS;rep++)); do
  if (( rep % 2 == 1 )); then treatments=("1:16" "2:16" "3:4" "3:8" "3:16"); else treatments=("3:16" "3:8" "3:4" "2:16" "1:16"); fi
  for treatment in "${treatments[@]}"; do
    producers="${treatment%%:*}"
    width="${treatment##*:}"
    name="r${rep}-p${producers}-w${width}"
    "$REPO/build/arm64/r9-multi-pipeline" --producers "$producers" --width "$width" --queue "$QUEUE" --seconds "$SEC" > "$RUN/measurements/$name.csv" 2> "$RUN/measurements/$name.err"
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
python3 "$REPO/tests/arm64-r9-pipeline-assess.py" "$RUN/measurements/results.csv" | tee "$RUN/assessment.txt"
