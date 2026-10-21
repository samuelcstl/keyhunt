#!/usr/bin/env bash
# Minimal end-to-end regression for the main fixed-width ECC backend on ARM64.
# Puzzle #20 private key d2c55 must be recovered from its legacy address.
set -euo pipefail
cd "$(dirname "$0")/.."
bin="${KEYHUNT_BIN:-keyhunt-arm64}"
if [[ ! -x "./$bin" ]]; then
  echo "Build first: missing $bin" >&2
  exit 1
fi
run_dir="$(mktemp -d)"
trap 'rm -rf "$run_dir"' EXIT
printf '%s\n' '1HsMJxNiV7TLxmoF6uJNkydxPFDog4NQum' > "$run_dir/target.txt"
cd "$run_dir"
timeout --signal=TERM --kill-after=5s 90s \
  "$OLDPWD/$bin" -m address -f "$run_dir/target.txt" \
  -r 80000:100000 -n 0x10000 -l compress -t 1 -s 0 \
  > run.log 2>&1 || { cat run.log; exit 1; }
cat run.log
grep -Eiq 'Hit! Private Key: 0*d2c55([^[:xdigit:]]|$)' run.log
echo 'PASS: puzzle #20 d2c55 recovered'
