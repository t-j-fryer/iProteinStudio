#!/usr/bin/env bash
# macOS acceptance test: prove the packaged app starts without SwiftPM's
# absolute build-machine resource fallback. This launches a GUI process briefly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${1:-${ROOT}/build/iProteinStudio.app}"
LOG="$(mktemp /tmp/iproteinstudio-clean-launch.XXXXXX)"
PID=""

restore() {
  if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
    kill "${PID}" 2>/dev/null || true
    wait "${PID}" 2>/dev/null || true
  fi
  rm -f -- "${LOG}"
}
trap restore EXIT

[[ -x "${APP}/Contents/MacOS/iProteinStudio" ]] \
  || { echo "FAIL packaged executable is missing: ${APP}" >&2; exit 1; }
APP="$(cd "$(dirname "${APP}")" && pwd)/$(basename "${APP}")"
cd /tmp
"${APP}/Contents/MacOS/iProteinStudio" >"${LOG}" 2>&1 &
PID=$!
sleep 5
if ! kill -0 "${PID}" 2>/dev/null; then
  wait "${PID}" || true
  sed -n '1,160p' "${LOG}" >&2
  echo "FAIL packaged app exited when launched away from its source checkout" >&2
  exit 1
fi

echo "PASS clean-machine packaged app startup"
