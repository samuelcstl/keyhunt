#!/usr/bin/env bash
# R10 physical Pi 5: 2-12 software threads on four physical A76 cores.
# Independent producer/consumer counts; each observation fully hashes keys.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${KEYHUNT_R10_RUN_DIR:-$REPO/../runs/arm64-r10-pipeline/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
SECONDS_PER_CONFIG="${KEYHUNT_R10_SECONDS:-60}"
REPEATS="${KEYHUNT_R10_REPEATS:-2}"
QUEUE="${KEYHUNT_R10_QUEUE:-32}"
WIDTH="${KEYHUNT_R10_WIDTH:-16}"
[[ ! -e "$RUN" ]] || { echo "Refusing existing run directory $RUN" >&2; exit 2; }
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || {
 echo "Refusing dirty tracked source" >&2;exit 2;
}
mkdir -p "$RUN"/{codegen,measurements}
chmod 700 "$RUN"
source "$REPO/tests/arm64-evidence-archive.sh"
trap 'kh_archive_on_exit "$?" "$RUN" r10-pipeline' EXIT
{
 date -u +%FT%TZ
 git -C "$REPO" rev-parse HEAD
 git -C "$REPO" branch --show-current
 uname -a
 g++ --version | head -1
 echo "seconds=$SECONDS_PER_CONFIG repeats=$REPEATS queue=$QUEUE width=$WIDTH"
 echo "physical cores 4, software threads configurable above four"
 echo "configurations=1:1 3:1 3:2 4:2 6:2 8:2 8:4"
} > "$RUN/provenance.txt"
for src in Makefile tests/arm64-r10-oversub-pipeline.cpp \
   tests/arm64-r10-oversub-screen.sh tests/arm64-r10-oversub-assess.py \
   secp256k1/IntGroup.cpp secp256k1/field_k1_arm64.cpp \
   hash/hash4_arm_sha2_su2.cpp hash/ripemd160_neon4.cpp; do
  mkdir -p "$RUN/codegen/$(dirname "$src")"
  cp "$REPO/$src" "$RUN/codegen/$src"
done
if command -v vcgencmd >/dev/null;then
 { vcgencmd get_throttled;vcgencmd measure_clock arm;vcgencmd measure_temp; } > "$RUN/host-before.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -35 > "$RUN/process-before.txt" || true
make -C "$REPO" -j4 arm64-r10-pipeline 2>&1 | tee "$RUN/build.log"
make -C "$REPO" arm64-r10-pipeline-test 2>&1 | tee "$RUN/correctness.log"
cp "$REPO/build/arm64/r10-oversub-pipeline" "$RUN/codegen/benchmark.bin"
sha256sum "$RUN/codegen/benchmark.bin" > "$RUN/codegen/binary.sha256"
objdump -drwC "$REPO/build/arm64/r10-oversub-pipeline" > "$RUN/codegen/disassembly.txt"
echo "repeat,producers,consumers,width,queue,mode,elapsed_s,produced_keys,hashed_keys,hashed_Mkeys_s,producer_inverse_ms,producer_points_ms,consumer_hash_ms,queue_full_ms,queue_empty_ms,peak_packets,hits" > "$RUN/measurements/results.csv"
for ((rep=1;rep<=REPEATS;rep++));do
 if (( rep%2 )); then
   configs=("1:1" "3:1" "3:2" "4:2" "6:2" "8:2" "8:4")
 else
   configs=("8:4" "8:2" "6:2" "4:2" "3:2" "3:1" "1:1")
 fi
 for config in "${configs[@]}";do
   producers="$(printf '%s' "$config" | cut -d: -f1)"
   consumers="$(printf '%s' "$config" | cut -d: -f2)"
   id="r${rep}-p${producers}-h${consumers}"
   bin="$REPO/build/arm64/r10-oversub-pipeline"
   "$bin" --producers "$producers" --consumers "$consumers" --width "$WIDTH" \
     --queue "$QUEUE" --seconds "$SECONDS_PER_CONFIG" \
     > "$RUN/measurements/$id.csv" 2>"$RUN/measurements/$id.err"
   tail -n1 "$RUN/measurements/$id.csv" | sed "s/^/$rep,/" >> "$RUN/measurements/results.csv"
   echo "Completed $id"
   tail -n1 "$RUN/measurements/$id.csv"
   if command -v vcgencmd >/dev/null;then
     { vcgencmd get_throttled;vcgencmd measure_clock arm;vcgencmd measure_temp; } > "$RUN/measurements/$id.sensor"
   fi
 done
done
if command -v vcgencmd >/dev/null;then
 { vcgencmd get_throttled;vcgencmd measure_clock arm;vcgencmd measure_temp; } > "$RUN/host-after.txt"
fi
ps -eo pid,ppid,stat,comm,%cpu --sort=-%cpu | head -35 > "$RUN/process-after.txt" || true
python3 "$REPO/tests/arm64-r10-oversub-assess.py" "$RUN/measurements/results.csv" | tee "$RUN/assessment.txt"
