#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh"
RFD3_INSTALL="${REPO_ROOT}/Sources/iProteinStudio/Resources/rfd3_overlay/install_rfd3.sh"
SWIFT_INSTALLER="${REPO_ROOT}/Sources/iProteinStudio/Core/PipelineInstaller.swift"
PROCESS_RUNNER="${REPO_ROOT}/Sources/iProteinStudio/Core/ProcessRunner.swift"
APP_PATHS="${REPO_ROOT}/Sources/iProteinStudio/Core/AppPaths.swift"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/iproteinstudio-hardening.XXXXXX")"
trap 'rm -rf "${TEST_ROOT}"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
expect() {
  local file="$1" literal="$2" message="$3"
  grep -Fq -- "${literal}" "${file}" || fail "${message}"
}

bash -n "${SETUP}"
bash -n "${RFD3_INSTALL}"

# Detection must distinguish a partially-created environment from a cleanly
# absent component. This executes the real read-only detection path.
mkdir -p "${TEST_ROOT}/partial/venvs/Test_boltz"
partial_output="$(NANOHUNTER_ROOT="${TEST_ROOT}/partial" NANOHUNTER_VENV_PREFIX=Test \
  bash "${SETUP}" --detect)"
printf '%s\n' "${partial_output}" | grep -Fq 'NHSTATE|boltz|incomplete|' \
  || fail "partial Boltz installation was not reported as incomplete"

# A live owner makes the atomic install lock non-recoverable. The setup command
# must fail before it mutates the managed root.
mkdir -p "${TEST_ROOT}/locked/.install.lock"
printf '%s\n' "$$" > "${TEST_ROOT}/locked/.install.lock/pid"
set +e
lock_output="$(NANOHUNTER_ROOT="${TEST_ROOT}/locked" NANOHUNTER_VENV_PREFIX=Test \
  bash "${SETUP}" --materialise 2>&1)"
lock_status=$?
set -e
[[ "${lock_status}" -ne 0 ]] || fail "second installer ignored the live install lock"
printf '%s\n' "${lock_output}" | grep -Fq 'already running' \
  || fail "install lock failure was not actionable"

# A dead owner's lock is recovered, and the maintenance path completes without
# needing network access or touching a real installation.
mkdir -p "${TEST_ROOT}/stale/.install.lock"
printf '999999\n' > "${TEST_ROOT}/stale/.install.lock/pid"
NANOHUNTER_ROOT="${TEST_ROOT}/stale" NANOHUNTER_VENV_PREFIX=Test \
  bash "${SETUP}" --materialise >/dev/null
[[ ! -e "${TEST_ROOT}/stale/.install.lock" ]] \
  || fail "stale installer lock was not released"

# These source assertions complement the behavioural checks above: the actual
# process-tree cancellation and transactional staging code is platform Swift and
# receives its compile check after the active benchmark finishes.
expect "${SWIFT_INSTALLER}" 'preventsSleep: true' "installer launch does not inhibit sleep"
expect "${SWIFT_INSTALLER}" 'logURL: log' "installer launch has no durable log"
expect "${PROCESS_RUNNER}" 'descendantPIDs' "Cancel would only terminate the parent shell"
expect "${APP_PATHS}" 'stageBundledItem' "pipeline resources are still replaced in place"
expect "${RFD3_INSTALL}" 'VERIFIED_DOWNLOADER' "RFD3 bypasses the verified downloader"
if grep -Eq 'curl .*CKPT_URL|CKPT_URL.*curl' "${RFD3_INSTALL}"; then
  fail "RFD3 checkpoint still uses its unverified curl path"
fi

echo "PASS installer hardening contract"
