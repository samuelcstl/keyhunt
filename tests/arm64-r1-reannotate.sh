#!/usr/bin/env bash
# Re-annotate an existing Pi perf.data without rerunning the workload.
# perf report may resolve symbols that perf annotate -s <short C++ name> misses.
set -euo pipefail
[[ $# == 1 ]] || { echo "usage: bash tests/arm64-r1-reannotate.sh <evidence-root>" >&2; exit 2; }
RUN="$(realpath "$1")"
[[ -d "$RUN/codegen" ]] || { echo "missing evidence codegen folder" >&2; exit 2; }
for name in keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1-neon keyhunt-r1-all; do
  dir="$RUN/codegen/profile-$name"
  data="$dir/perf.data"
  [[ -s "$data" ]] || { echo "missing perf data $data" >&2; exit 2; }
  # First validate that samples exist rather than mistaking a symbol mismatch
  # for failure to record performance events.
  perf report -i "$data" --stdio --no-children --sort=symbol > "$dir/report-reannotate.txt"
  if ! grep -Eq '^# Samples: [1-9][0-9]*[KMG]? of event' "$dir/report-reannotate.txt"; then
    echo "ERROR: perf report did not show samples for $name" >&2
    exit 1
  fi
  for entry in thread mul; do
    if [[ "$entry" == thread ]]; then
      symbol='thread_process(void*)'
    else
      symbol='field_k1_arm64_mul(unsigned long*, unsigned long const*, unsigned long const*)'
    fi
    output="$dir/$entry-assembly-recovered.txt"
    perf annotate -i "$data" --stdio --symbol "$symbol" > "$output" 2>&1 || true
    if grep -qiE 'has no samples|error:|no (assembly|source)' "$output" || [[ ! -s "$output" ]]; then
      echo "WARN: perf annotate could not resolve exact C++ symbol $symbol in $name" >&2
      # Keep raw symbol/sample evidence and the existing full objdump. Never
      # pretend an unsuccessful annotate produced instruction-level attribution.
      printf 'ANNOTATE_UNAVAILABLE for %s\n' "$symbol" > "$dir/$entry-annotation-status.txt"
    else
      printf 'ANNOTATE_AVAILABLE for %s\n' "$symbol" > "$dir/$entry-annotation-status.txt"
    fi
  done
done
echo "Reannotation attempted. Check recovered files and *_annotation-status.txt."
echo "If perf cannot associate samples with local binaries, preserve raw perf.data;"
echo "the disassembly snapshots still show codegen but not sample weight per instruction."
