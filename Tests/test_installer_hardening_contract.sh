#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh"
RFD3_INSTALL="${REPO_ROOT}/Sources/iProteinStudio/Resources/rfd3_overlay/install_rfd3.sh"
SWIFT_INSTALLER="${REPO_ROOT}/Sources/iProteinStudio/Core/PipelineInstaller.swift"
PROCESS_RUNNER="${REPO_ROOT}/Sources/iProteinStudio/Core/ProcessRunner.swift"
APP_PATHS="${REPO_ROOT}/Sources/iProteinStudio/Core/AppPaths.swift"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/iproteinstudio-hardening.XXXXXX")"
BUSY_PID=""
trap '[[ -z "${BUSY_PID}" ]] || kill "${BUSY_PID}" 2>/dev/null || true; rm -rf "${TEST_ROOT}"' EXIT

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

# Engine updates must refuse to overlap an active predictor process. A symlinked
# sleep binary gives pgrep a real command line under the synthetic managed venv.
mkdir -p "${TEST_ROOT}/busy/venvs/Test_active/bin"
ln -s /bin/sleep "${TEST_ROOT}/busy/venvs/Test_active/bin/model-worker"
"${TEST_ROOT}/busy/venvs/Test_active/bin/model-worker" 30 &
BUSY_PID=$!
set +e
busy_output="$(NANOHUNTER_ROOT="${TEST_ROOT}/busy" NANOHUNTER_VENV_PREFIX=Test \
  bash "${SETUP}" --materialise 2>&1)"
busy_status=$?
set -e
kill "${BUSY_PID}" 2>/dev/null || true
wait "${BUSY_PID}" 2>/dev/null || true
BUSY_PID=""
[[ "${busy_status}" -ne 0 ]] || fail "installer overlapped an active managed runtime"
printf '%s\n' "${busy_output}" | grep -Fq 'using the managed runtime' \
  || fail "active-runtime refusal was not actionable"

# These source assertions complement the behavioural checks above: the actual
# process-tree cancellation and transactional staging code is platform Swift and
# receives its compile check after the active benchmark finishes.
expect "${SWIFT_INSTALLER}" 'preventsSleep: true' "installer launch does not inhibit sleep"
expect "${SWIFT_INSTALLER}" 'logURL: log' "installer launch has no durable log"
expect "${PROCESS_RUNNER}" 'descendantPIDs' "Cancel would only terminate the parent shell"
expect "${APP_PATHS}" 'stageBundledItem' "pipeline resources are still replaced in place"
expect "${RFD3_INSTALL}" 'VERIFIED_DOWNLOADER' "RFD3 bypasses the verified downloader"
expect "${SETUP}" 'UV_VERSION="0.11.32"' "managed uv is not exactly pinned"
expect "${SETUP}" 'UV_PYTHON_INSTALL_DIR=' "managed Python can escape Studio's root"
expect "${SETUP}" 'pip install --require-hashes' "engine dependency graphs are not hash-enforced"
expect "${SETUP}" 'download_intellifold' "IntelliFold bypasses the resumable downloader"
expect "${SETUP}" 'https://openfold.s3.amazonaws.com/' "OpenFold bypasses the resumable downloader"
expect "${SETUP}" 'runtime_transaction.py' "versioned environment transactions are absent"
expect "${SETUP}" 'component_receipt.py' "component receipts are absent"
expect "${SETUP}" 'shared/protenix-common' "Protenix common data is still duplicated"
if grep -Eq 'curl .*CKPT_URL|CKPT_URL.*curl' "${RFD3_INSTALL}"; then
  fail "RFD3 checkpoint still uses its unverified curl path"
fi

echo "PASS installer hardening contract"
