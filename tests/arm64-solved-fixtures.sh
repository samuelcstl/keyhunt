#!/usr/bin/env bash
# Exercise the upstream repository's solved-puzzle address fixtures,
# not just the one-address synthetic test.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
bin="${KEYHUNT_BIN:-keyhunt-arm64}"
if [[ ! -x "$repo/$bin" ]]; then
  echo "Missing binary: $repo/$bin" >&2
  exit 1
fi
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
timeout --signal=TERM --kill-after=5s 45s \
  "$repo/$bin" -m address -f "$repo/tests/1to32.txt" \
  -r 1:4000 -n 0x400 -l compress -t 1 -q -s 0 \
  > run.log 2>&1 || { tail -100 run.log; exit 1; }

# These first solved addresses and keys are independently documented in
# upstream's README; they also appear in tests/1to32.txt.
for scalar in 1 3 7; do
  if ! grep -Eiq "Hit! Private Key: 0*${scalar}([^[:xdigit:]]|$)" run.log; then
    echo "Missing solved-puzzle scalar: $scalar" >&2
    tail -100 run.log
    exit 1
  fi
done

grep 'Hit! Private Key:' run.log | head -15
echo "PASS: upstream solved-puzzle fixtures #1/#2/#3 recovered"
