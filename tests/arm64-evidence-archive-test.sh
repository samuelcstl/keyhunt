#!/usr/bin/env bash
# A quick filesystem-only test. Does NOT build or run any cryptographic code.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
export KEYHUNT_EVIDENCE_ARCHIVE_DIR="$TEMP/out"
mkdir -p "$TEMP/success" "$TEMP/failure"
printf 'correctness=PASS\n' > "$TEMP/success/validations.log"
printf 'compile failed in test\n' > "$TEMP/failure/build.log"

(
  source "$HERE/tests/arm64-evidence-archive.sh"
  RUN="$TEMP/success"
  trap 'kh_archive_on_exit "$?" "$RUN" test-success' EXIT
  true
)
GOOD="$TEMP/out/test-success-results-success.tar.gz"
[[ -s "$GOOD" && -s "$GOOD.sha256" ]]
( cd "$TEMP/out" && sha256sum -c "$(basename "$GOOD").sha256" >/dev/null )
mkdir "$TEMP/unpacked-success"
tar -xzf "$GOOD" -C "$TEMP/unpacked-success"
grep -qx 'status=completed' "$TEMP/unpacked-success/success/run-status.txt"
grep -qx 'exit_code=0' "$TEMP/unpacked-success/success/run-status.txt"
( cd "$TEMP/unpacked-success/success" && sha256sum -c SHA256SUMS >/dev/null )

if (
  source "$HERE/tests/arm64-evidence-archive.sh"
  RUN="$TEMP/failure"
  trap 'kh_archive_on_exit "$?" "$RUN" test-failure' EXIT
  exit 23
); then
  echo "FAIL: simulated failed benchmark unexpectedly exited 0" >&2
  exit 1
else
  exit_status=$?
  [[ "$exit_status" == 23 ]] || { echo "FAIL: expected exit 23, got $exit_status" >&2; exit 1; }
fi
BAD="$TEMP/out/test-failure-results-failure.tar.gz"
[[ -s "$BAD" && -s "$BAD.sha256" ]]
( cd "$TEMP/out" && sha256sum -c "$(basename "$BAD").sha256" >/dev/null )
mkdir "$TEMP/unpacked-failure"
tar -xzf "$BAD" -C "$TEMP/unpacked-failure"
grep -qx 'status=failed' "$TEMP/unpacked-failure/failure/run-status.txt"
grep -qx 'exit_code=23' "$TEMP/unpacked-failure/failure/run-status.txt"
( cd "$TEMP/unpacked-failure/failure" && sha256sum -c SHA256SUMS >/dev/null )

echo 'PASS: automatic archive, SHA256 integrity, and original failure exit code'
