#!/usr/bin/env bash
# Source from ARM64 experimental benchmark runners only.
# Usage: trap 'kh_archive_on_exit "$?" "$RUN" r3-ecc' EXIT
# All partial results are preserved even if a test exits nonzero.
kh_archive_on_exit() {
  local original_status="${1:-1}"
  local run_dir="${2:-}"
  local experiment="${3:-experiment}"
  trap - EXIT
  set +e
  if [[ -z "$run_dir" || ! -d "$run_dir" ]]; then
    echo "[archive] No run directory was created." >&2
    exit "$original_status"
  fi

  local absolute_run
  absolute_run="$(cd "$run_dir" && pwd -P)"
  local base parent
  base="$(basename "$absolute_run")"
  parent="$(dirname "$absolute_run")"
  local status=completed
  if (( original_status != 0 )); then status=failed; fi
  {
    printf 'status=%s\n' "$status"
    printf 'exit_code=%s\n' "$original_status"
    printf 'utc_finished=%s\n' "$(date -u +%FT%TZ)"
    printf 'experiment=%s\n' "$experiment"
  } > "$absolute_run/run-status.txt"

  local dir="${KEYHUNT_EVIDENCE_ARCHIVE_DIR:-$HOME}"
  local archive="$dir/${experiment}-results-${base}.tar.gz"
  local partial="${archive}.partial.$$"
  local failure=0
  mkdir -p "$dir" || failure=1
  if (( failure == 0 )); then
    (
      cd "$absolute_run" || exit 1
      find . -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z \
        | xargs -0 -r sha256sum > SHA256SUMS || exit 1
      sha256sum -c SHA256SUMS >/dev/null
    ) || failure=1
  fi
  if (( failure == 0 )); then
    tar -czf "$partial" -C "$parent" "$base" || failure=1
  fi
  if (( failure == 0 )); then
    tar -tzf "$partial" >/dev/null || failure=1
  fi
  if (( failure == 0 )); then
    mv -f "$partial" "$archive" || failure=1
  fi
  if (( failure == 0 )); then
    ( cd "$dir" && sha256sum "$(basename "$archive")" \
      > "$(basename "$archive").sha256" ) || failure=1
  fi
  rm -f "$partial"
  if (( failure == 0 )); then
    echo
    echo "[archive] Run status: $status (exit=$original_status)"
    echo "[archive] Full evidence: $archive"
    echo "[archive] SHA256 file: ${archive}.sha256"
    echo "[archive] Send the .tar.gz directly; no terminal output needed."
  else
    echo "[archive] ERROR: archive creation/verification failed." >&2
    echo "[archive] Raw evidence still available: $absolute_run" >&2
    if (( original_status == 0 )); then exit 70; fi
  fi
  exit "$original_status"
}
