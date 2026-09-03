#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh"
RFD3_INSTALL="${REPO_ROOT}/Sources/iProteinStudio/Resources/rfd3_overlay/install_rfd3.sh"
SWIFT_INSTALLER="${REPO_ROOT}/Sources/iProteinStudio/Core/PipelineInstaller.swift"
PROCESS_RUNNER="${REPO_ROOT}/Sources/iProteinStudio/Core/ProcessRunner.swift"
APP_PATHS="${REPO_ROOT}/Sources/iProteinStudio/Core/AppPaths.swift"
ANTIFOLD_LOCK="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/locks/antifold.txt"
LASERMPNN_BOOTSTRAP_LOCK="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/locks/lasermpnn_bootstrap.txt"
RUNTIME_TRANSACTION="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/runtime_transaction.py"
COMPONENT_RECEIPT="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/component_receipt.py"
COMPONENTS_VIEW="${REPO_ROOT}/Sources/iProteinStudio/Views/Onboarding/ComponentsView.swift"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/iproteinstudio-hardening.XXXXXX")"
BUSY_PID=""
trap '[[ -z "${BUSY_PID}" ]] || kill "${BUSY_PID}" 2>/dev/null || true; rm -rf "${TEST_ROOT}"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
make_executable() {
  mkdir -p "$(dirname "$1")"
  printf '#!/bin/sh\nexit 0\n' > "$1"
  chmod +x "$1"
}
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

# A file named like RFdiffusion3 weights is not enough: old Studio builds
# exported the raw network. Detection (shared by the app and MCP) must reject
# missing/incorrect EMA provenance before any campaign can claim readiness.
make_executable "${TEST_ROOT}/rfd3-receipt/rfd3/.venv/bin/python"
mkdir -p "${TEST_ROOT}/rfd3-receipt/rfd3/checkpoints" \
  "${TEST_ROOT}/rfd3-receipt/rfd3/weights"
printf 'checkpoint\n' > "${TEST_ROOT}/rfd3-receipt/rfd3/checkpoints/rfd3_latest.ckpt"
printf 'weights\n' > "${TEST_ROOT}/rfd3-receipt/rfd3/weights/rfd3_core.safetensors"
rfd3_receipt_output="$(NANOHUNTER_ROOT="${TEST_ROOT}/rfd3-receipt" \
  NANOHUNTER_VENV_PREFIX=Test bash "${SETUP}" --detect)"
printf '%s\n' "${rfd3_receipt_output}" | grep -Fq \
  'NHSTATE|rfd3|update|exported weights are not verified EMA shadow weights; repair RFdiffusion3 before use' \
  || fail "unverified RFdiffusion3 weights were reported as usable"

# A verified EMA artifact remains usable when only the final receipt write was
# interrupted; setup should offer to finalize provenance rather than hide it.
cp "$(dirname "${SETUP}")/../rfd3_overlay/rfd3_weight_set.py" \
  "${TEST_ROOT}/rfd3-receipt/rfd3/rfd3_weight_set.py"
python3 - "${TEST_ROOT}/rfd3-receipt/rfd3/weights/rfd3_core.safetensors" <<'PY'
import json, pathlib, struct, sys
path = pathlib.Path(sys.argv[1])
header = json.dumps({"__metadata__": {
    "source": "rfd3_latest.ckpt", "weight_set": "shadow", "which": "shadow (EMA)"
}}, separators=(",", ":")).encode()
path.write_bytes(struct.pack("<Q", len(header)) + header)
PY
rfd3_receipt_output="$(NANOHUNTER_ROOT="${TEST_ROOT}/rfd3-receipt" \
  NANOHUNTER_VENV_PREFIX=Test bash "${SETUP}" --detect)"
printf '%s\n' "${rfd3_receipt_output}" | grep -Fq \
  'NHSTATE|rfd3|update|engine is usable; installation provenance still needs finalizing' \
  || fail "receipt-less verified RFdiffusion3 was not offered a repair"

# A failed dependency install leaves only a private, uncommitted transaction
# stage. A retry must remove that owned stage before creating the replacement,
# while the helper's marker checks prevent broad or speculative deletion.
first_stage="$(python3 "${RUNTIME_TRANSACTION}" prepare \
  --root "${TEST_ROOT}/transactions" --component antifold --version test-v1)"
[[ -d "${first_stage}" ]] || fail "first transaction stage was not created"
unknown_stage="$(dirname "${first_stage}")/.staging-unknown"
mkdir -p "${unknown_stage}"
second_stage="$(python3 "${RUNTIME_TRANSACTION}" prepare \
  --root "${TEST_ROOT}/transactions" --component antifold --version test-v1)"
[[ ! -e "${first_stage}" ]] || fail "retry retained an installer-owned failed stage"
[[ -d "${second_stage}" ]] || fail "retry did not create a replacement transaction stage"
[[ -d "${unknown_stage}" ]] || fail "retry deleted an unowned or malformed stage"

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
expect "${SETUP}" 'uv_install_locked' "engines do not share uv's clone-backed package store"
expect "${SETUP}" '--require-hashes' "engine dependency graphs are not hash-enforced"
expect "${ANTIFOLD_LOCK}" 'setuptools==79.0.1' "AntiFold editable-install backend is not pinned"
if grep -Eq '^wheel==' "${ANTIFOLD_LOCK}"; then
  fail "AntiFold lock contains unnecessary wheel; wheel 0.48 adds an uncompiled packaging dependency"
fi
expect "${LASERMPNN_BOOTSTRAP_LOCK}" 'sha256:7f0ca4bcc0e181c60dbbd8aa9ab5b120ebb99e4e064e83636340056f833a1f09' \
  "LASErMPNN bootstrap omits the published filelock 3.32.3 wheel hash"
expect "${LASERMPNN_BOOTSTRAP_LOCK}" 'sha256:0ffa185a3540854c95caa7fa76b76cb219d907415e2c5dc9af25fd970563487f' \
  "LASErMPNN bootstrap omits the published filelock 3.32.3 source hash"
if grep -Eq 'local model_dir="\$1"[^$]*\$\{model_dir\}' "${SETUP}"; then
  fail "Protenix helper expands a nounset local in the declaration that creates it"
fi
expect "${COMPONENT_RECEIPT}" 'package_inventory_method' \
  "pip-less runtimes cannot record a durable package inventory"
expect "${COMPONENTS_VIEW}" 'ProteinMPNN · SolubleMPNN · LigandMPNN · AbMPNN' \
  "Engines hides which sequence designers are installed as the core suite"
expect "${SETUP}" 'download_intellifold' "IntelliFold bypasses the resumable downloader"
expect "${SETUP}" 'https://openfold.s3.amazonaws.com/' "OpenFold bypasses the resumable downloader"
expect "${SETUP}" 'runtime_transaction.py' "versioned environment transactions are absent"
expect "${SETUP}" 'component_receipt.py' "component receipts are absent"
expect "${SETUP}" 'shared/protenix-common' "Protenix common data is still duplicated"
expect "${SETUP}" 'shared/git-objects' "duplicate source checkouts do not share Git objects"
expect "${SETUP}" 'managed_storage.py' "existing installs have no verified deduplication path"
if grep -Eq 'curl .*CKPT_URL|CKPT_URL.*curl' "${RFD3_INSTALL}"; then
  fail "RFD3 checkpoint still uses its unverified curl path"
fi

echo "PASS installer hardening contract"
