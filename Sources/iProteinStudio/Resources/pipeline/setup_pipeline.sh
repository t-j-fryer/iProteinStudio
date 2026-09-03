#!/usr/bin/env bash
# iProteinStudio pipeline setup.
#
# Installs the design backends into the app's managed directory. Sequence
# designers are unconditional; folding, guided-design and backbone engines are
# selected by the app because they cost gigabytes.
#
#   Always   LigandMPNN family (+ AbMPNN, ProteinMPNN and SolubleMPNN)
#   Selected --with-boltz            Boltz-2 structure model
#            --with-boltz-affinity   optional small-molecule affinity model
#            --with-antifold         AntiFold
#            --with-intellifold      IntelliFold v2 Flash PyTorch/Metal
#            --with-intellifold-full optional full-v2 checkpoint
#            --with-openfold3        OpenFold-3-MLX      (~2.1 GB checkpoint)
#            --with-protenix-v2      Protenix v2          (native MPS, GPU-only)
#            --with-protenix-mini    Protenix Mini        (native MPS, GPU-only)
#            --with-protenix-constraint
#                                    Protenix Constraint v0.5 (separate,
#                                    experimental design-only checkpoint)
#            --with-rfd3             RFdiffusion3 on MLX (~1.3 GB checkpoint)
#
# Reuse instead of reinstall:
#
#   --link-existing PATH    Point the app at an existing NanoHunter checkout's
#                           venvs/, src/ and models/ via symlink. Saves tens of
#                           GB and many minutes on a machine that already has
#                           NanoHunter installed. The app still uses its own
#                           vendored runner and examples.
#   --detect                Print what is already installed and exit.
#
# Emits machine-parseable progress on stdout so the app can render a friendly
# setup wizard:
#   NHSTEP|<key>|<0-100 pct>|<human message>
#   NHSTATE|<component>|<ok|missing|skipped>|<detail>
#   NHDONE|ok
#   NHFAIL|<message>
set -uo pipefail

# CLI installs deserve the same sleep protection as GUI installs. Detection and
# help are read-only and fast, so do not spawn a keep-awake process for them.
if [[ "${IPROTEINSTUDIO_SETUP_CAFFEINATED:-0}" != "1" ]] \
   && command -v caffeinate >/dev/null 2>&1; then
  KEEP_AWAKE=1
  for setup_arg in "$@"; do
    case "${setup_arg}" in --detect|-h|--help) KEEP_AWAKE=0 ;; esac
  done
  if [[ "${KEEP_AWAKE}" -eq 1 ]]; then
    exec env IPROTEINSTUDIO_SETUP_CAFFEINATED=1 \
      caffeinate -dimsu /bin/bash "$0" "$@"
  fi
fi

NANOHUNTER_ROOT="${NANOHUNTER_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
VENV_PREFIX="${NANOHUNTER_VENV_PREFIX:-NanoHunter}"
PYTHON_311_VERSION="3.11.13"
PYTHON_310_VERSION="3.10.18"
PYTHON_312_VERSION="3.12.11"
PYTHON_BIN=""
ANTIFOLD_PYTHON_BIN=""
INTELLIFOLD_PYTHON_BIN=""
UV_VERSION="0.11.32"
UV_SHA256="ed336d0ba49db8ef89b2b41fffa372ce63bd032f22a56f001c265891aec32829"
TOOLCHAIN_DIR="${NANOHUNTER_ROOT}/toolchains"
UV_HOME="${TOOLCHAIN_DIR}/uv/${UV_VERSION}"
UV_BIN="${UV_HOME}/uv"
export UV_PYTHON_INSTALL_DIR="${TOOLCHAIN_DIR}/python"
export UV_PYTHON_BIN_DIR="${TOOLCHAIN_DIR}/python-bin"
export UV_CACHE_DIR="${NANOHUNTER_ROOT}/cache/uv"
export PIP_CACHE_DIR="${NANOHUNTER_ROOT}/cache/pip"
export UV_MANAGED_PYTHON=1

# Source and package versions validated by the isolated-install acceptance run
# recorded in Lab Book 0013.  A setup script that clones moving default branches
# cannot recreate a run a month later, even when every output lives under the
# managed root.
BOLTZ_VERSION="2.2.1"
BOLTZ_TORCH_VERSION="2.13.0"
LIGANDMPNN_REV="26ec57ac976ade5379920dbd43c7f97a91cf82de"
ANTIFOLD_REV="789d46786624c01eb44f177ef4c0deeeb6e77469"
INTELLIFOLD_REV="4e420db7482b4f50dbb86800ff710ee4ec7c7b7b"
LASERMPNN_REV="5df210fced6764d83f01425d1fc4319a22b70c2a"
OPENFOLD_REV="eeac37eb82dc2b80cf043eb26105a16d2493d052"
RFD3_REV="47a42e8f40207e66b994d4863f9b1911f1bc36eb"
PROTENIX_REV="4c355be4553512f72453ecbfb65e69f4c35d1413" # upstream 2.0.0

# Every engine is opt-in. Only the sequence designers are unconditional.
WITH_BOLTZ=0
WITH_BOLTZ_AFFINITY=0
WITH_ANTIFOLD=0
WITH_INTELLIFOLD=0
WITH_INTELLIFOLD_FULL=0
WITH_PROTENIX_RUNTIME=0
WITH_PROTENIX_V2=0
WITH_PROTENIX_MINI=0
WITH_PROTENIX_CONSTRAINT=0
WITH_OPENFOLD3=0
WITH_RFD3=0
WITH_LASERMPNN=0
MATERIALISE=0
REPAIR_VENVS=0
MINIMIZE_STORAGE=0
LINK_EXISTING=""
LINK_RFD3=""
DETECT_ONLY=0

usage() {
  cat <<'EOF'
Usage: setup_pipeline.sh [components | maintenance]

Components (combine as needed):
  --with-boltz                 Boltz-2 structure prediction and steering
  --with-boltz-affinity        Optional small-molecule affinity checkpoint
  --with-antifold              AntiFold nanobody sequence design
  --with-intellifold           IntelliFold v2 Flash PyTorch/Metal
  --with-intellifold-full      Optional IntelliFold full-v2 checkpoint
  --with-protenix-runtime      Shared Protenix runtime/data (normally automatic)
  --with-protenix-v2           Protenix v2 prediction checkpoint
  --with-protenix-mini         Protenix Mini prediction checkpoint
  --with-protenix              Legacy alias selecting v2 and Mini
  --with-protenix-constraint   Experimental Protenix Constraint v0.5
                               protein-epitope design checkpoint (separate,
                               native MPS, design-only, no CPU fallback)
  --with-openfold3             OpenFold-3/MLX
  --with-lasermpnn             LASErMPNN ligand sequence design
  --with-rfd3                  RFdiffusion3/MLX (also selects Boltz)
  --all                        Install every supported component

Maintenance:
  --detect                     Report installed component state
  --link-existing PATH         Reuse components from an installed NanoHunter root
  --link-rfd3 PATH             Reuse an installed RFdiffusion3 checkout
  --materialise                Replace managed component links with local copies
  --repair-venvs               Repair absolute paths after moving an installation
  --minimize-storage           Share verified duplicate assets in an existing install
  -h, --help                   Show this help

The MPNN sequence-designer family is installed for every non-maintenance setup.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-boltz)           WITH_BOLTZ=1; shift ;;
    --with-boltz-affinity)  WITH_BOLTZ=1; WITH_BOLTZ_AFFINITY=1; shift ;;
    --with-antifold)        WITH_ANTIFOLD=1; shift ;;
    --with-intellifold)     WITH_INTELLIFOLD=1; shift ;;
    --with-intellifold-full) WITH_INTELLIFOLD=1; WITH_INTELLIFOLD_FULL=1; shift ;;
    --with-protenix-runtime) WITH_PROTENIX_RUNTIME=1; shift ;;
    --with-protenix-v2)     WITH_PROTENIX_RUNTIME=1; WITH_PROTENIX_V2=1; shift ;;
    --with-protenix-mini)   WITH_PROTENIX_RUNTIME=1; WITH_PROTENIX_MINI=1; shift ;;
    --with-protenix)        WITH_PROTENIX_RUNTIME=1; WITH_PROTENIX_V2=1; WITH_PROTENIX_MINI=1; shift ;;
    --with-protenix-constraint) WITH_PROTENIX_CONSTRAINT=1; shift ;;
    --with-openfold3)       WITH_OPENFOLD3=1; shift ;;
    --with-alphafold3|--with-intellifold-jax)
      echo "NHFAIL|AlphaFold 3 and IntelliFold JAX were retired after Metal quality-control failures."
      exit 2 ;;
    --with-rfd3)            WITH_RFD3=1; WITH_BOLTZ=1; shift ;;
    --link-existing)        LINK_EXISTING="$2"; shift 2 ;;
    --materialise|--materialize) MATERIALISE=1; shift ;;
    --all)                  WITH_BOLTZ=1; WITH_BOLTZ_AFFINITY=1; WITH_ANTIFOLD=1
                            WITH_INTELLIFOLD=1; WITH_INTELLIFOLD_FULL=1
                            WITH_OPENFOLD3=1; WITH_PROTENIX_RUNTIME=1
                            WITH_PROTENIX_V2=1; WITH_PROTENIX_MINI=1; WITH_PROTENIX_CONSTRAINT=1
                            WITH_LASERMPNN=1; WITH_RFD3=1; shift ;;
    --with-lasermpnn)       WITH_LASERMPNN=1; shift ;;
    --link-rfd3)            LINK_RFD3="$2"; shift 2 ;;
    --detect)               DETECT_ONLY=1; shift ;;
    --repair-venvs)         REPAIR_VENVS=1; shift ;;
    --minimize-storage)     MINIMIZE_STORAGE=1; shift ;;
    -h|--help)              usage; exit 0 ;;
    *) echo "NHFAIL|Unknown option: $1"; exit 2 ;;
  esac
done

SRC_DIR="${NANOHUNTER_ROOT}/src"
BOLTZ_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_boltz"
LIGAND_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_ligandmpnn"
ANTIFOLD_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_antifold"
INTELLIFOLD_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_intellifold"
PROTENIX_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_protenix"
PROTENIX_CONSTRAINT_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_protenix_constraint"
OPENFOLD_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_openfold3_mlx"
LIGANDMPNN_REPO="${SRC_DIR}/LigandMPNN"
ANTIFOLD_REPO="${SRC_DIR}/AntiFold"
INTELLIFOLD_REPO="${SRC_DIR}/IntelliFold"
PROTENIX_REPO="${SRC_DIR}/Protenix"
PROTENIX_CONSTRAINT_REPO="${SRC_DIR}/ProtenixConstraint"
OPENFOLD_REPO="${SRC_DIR}/openfold-3-mlx"
BOLTZ_MODEL_DIR="${NANOHUNTER_ROOT}/models/boltz2"
NUMBA_CACHE_DIR="${NANOHUNTER_ROOT}/numba_cache"
INTELLIFOLD_MODEL_DIR="${NANOHUNTER_ROOT}/models/intellifold"
PROTENIX_MODEL_DIR="${NANOHUNTER_ROOT}/models/protenix"
PROTENIX_CONSTRAINT_MODEL_DIR="${NANOHUNTER_ROOT}/models/protenix_constraint"
PROTENIX_COMMON_DIR="${NANOHUNTER_ROOT}/shared/protenix-common/v0.5"
OPENFOLD_MODEL_DIR="${NANOHUNTER_ROOT}/models/openfold3"
OPENFOLD_CHECKPOINT_PATH="${OPENFOLD_MODEL_DIR}/of3_ft3_v1.pt"
RFD3_ROOT="${NANOHUNTER_ROOT}/rfd3"
RFD3_CHECKPOINT_PATH="${RFD3_ROOT}/checkpoints/rfd3_latest.ckpt"
RFD3_WEIGHTS_PATH="${RFD3_ROOT}/weights/rfd3_core.safetensors"
RFD3_WEIGHTS_SHA="736e6f5e11ec70dea58903deb2290031e366d2b0b2478e63208a2541650a04d6"
# Staged out of the app bundle next to this script; absent when the script is
# run standalone, in which case the overlay step is simply skipped.
STUDIO_RFD3_OVERLAY="${NANOHUNTER_ROOT}/rfd3_overlay"
INTELLIFOLD_STUDIO_PATCH="${NANOHUNTER_ROOT}/patches/intellifold_pytorch_mps.patch"
PROTENIX_STUDIO_PATCH="${NANOHUNTER_ROOT}/patches/protenix_mps.patch"
PROTENIX_CONSTRAINT_PATCH="${NANOHUNTER_ROOT}/patches/protenix_constraint_mps.patch"
PROTENIX_CONSTRAINT_ZERO_SUBSTRUCTURE_PATCH="${NANOHUNTER_ROOT}/patches/protenix_constraint_zero_substructure.patch"
LOCK_DIR="${NANOHUNTER_ROOT}/locks"
BOLTZ_LOCK="${LOCK_DIR}/boltz.txt"
MPNN_LOCK="${LOCK_DIR}/mpnn.txt"
ANTIFOLD_LOCK="${LOCK_DIR}/antifold.txt"
INTELLIFOLD_LOCK="${LOCK_DIR}/intellifold.txt"
PROTENIX_LOCK="${LOCK_DIR}/protenix.txt"
PROTENIX_CONSTRAINT_LOCK="${LOCK_DIR}/protenix_constraint.txt"
LASERMPNN_LOCK="${LOCK_DIR}/lasermpnn.txt"
LASERMPNN_BOOTSTRAP_LOCK="${LOCK_DIR}/lasermpnn_bootstrap.txt"
OPENFOLD_LOCK="${LOCK_DIR}/openfold3.txt"
VERIFIED_DOWNLOADER="${NANOHUNTER_ROOT}/scripts/download_verified.py"
COMPONENT_RECEIPT="${NANOHUNTER_ROOT}/scripts/component_receipt.py"
RUNTIME_TRANSACTION="${NANOHUNTER_ROOT}/scripts/runtime_transaction.py"
MANAGED_STORAGE="${NANOHUNTER_ROOT}/scripts/managed_storage.py"
INSTALL_LOCK="${NANOHUNTER_ROOT}/.install.lock"
RECEIPTS_DIR="${NANOHUNTER_ROOT}/receipts"

step()  { echo "NHSTEP|$1|$2|$3"; }
state() { echo "NHSTATE|$1|$2|$3"; }
fail()  { echo "NHFAIL|$1"; exit 1; }

state_absent_or_partial() {
  local key="$1" detail="$2"; shift 2
  local any=0 broken=0 path
  for path in "$@"; do
    [[ -e "${path}" || -L "${path}" ]] && any=1
    [[ -L "${path}" && ! -e "${path}" ]] && broken=1
  done
  if [[ "${broken}" -eq 1 ]]; then
    state "${key}" broken "a linked environment, source, or model target is missing"
  elif [[ "${any}" -eq 1 ]]; then
    state "${key}" incomplete "${detail}"
  else
    state "${key}" missing "${detail}"
  fi
}

release_install_lock() {
  [[ -d "${INSTALL_LOCK}" ]] || return 0
  local owner=""
  [[ -f "${INSTALL_LOCK}/pid" ]] && owner="$(cat "${INSTALL_LOCK}/pid" 2>/dev/null || true)"
  [[ "${owner}" == "$$" ]] || return 0
  rm -f "${INSTALL_LOCK}/pid"
  rmdir "${INSTALL_LOCK}" 2>/dev/null || true
}

acquire_install_lock() {
  mkdir -p "${NANOHUNTER_ROOT}"
  if ! mkdir "${INSTALL_LOCK}" 2>/dev/null; then
    local owner=""
    [[ -f "${INSTALL_LOCK}/pid" ]] && owner="$(cat "${INSTALL_LOCK}/pid" 2>/dev/null || true)"
    if [[ "${owner}" =~ ^[0-9]+$ ]] && kill -0 "${owner}" 2>/dev/null; then
      fail "Another Studio installation or repair is already running (process ${owner})."
    fi
    # Recover only a lock whose recorded owner no longer exists. rmdir refuses
    # anything except the known pid file, so unrelated contents are preserved.
    rm -f "${INSTALL_LOCK}/pid"
    rmdir "${INSTALL_LOCK}" 2>/dev/null \
      || fail "The installer lock is stale but could not be recovered: ${INSTALL_LOCK}"
    mkdir "${INSTALL_LOCK}" 2>/dev/null \
      || fail "Another Studio installation started at the same time."
  fi
  printf '%s\n' "$$" > "${INSTALL_LOCK}/pid"
  trap release_install_lock EXIT
}

ensure_pinned_repo() {
  local label="$1" url="$2" revision="$3" target="$4" actual=""
  if git -C "${target}" rev-parse --git-dir >/dev/null 2>&1; then
    actual="$(git -C "${target}" rev-parse HEAD 2>/dev/null || true)"
    [[ "${actual}" == "${revision}" ]] && return 0
  fi

  local parent stage backup_root backup mirror_key mirror
  parent="$(dirname "${target}")"
  mkdir -p "${parent}"
  stage="${parent}/.stage-$(basename "${target}")-$$"
  [[ ! -e "${stage}" ]] || fail "A stale source stage needs attention: ${stage}"
  # Keep one object store per upstream URL. Standard and Constraint Protenix
  # need separate patched worktrees, but not two identical copies of Git's
  # history. Each checkout explicitly references only this managed, non-cache
  # object store; clearing download caches therefore cannot break a checkout.
  mirror_key="$(printf '%s' "${url}" | shasum -a 256 | awk '{print $1}')"
  mirror="${NANOHUNTER_ROOT}/shared/git-objects/${mirror_key}.git"
  if [[ ! -d "${mirror}" ]]; then
    mkdir -p "$(dirname "${mirror}")"
    git init -q --bare "${mirror}" || fail "${label} shared source store creation failed."
    git --git-dir="${mirror}" remote add origin "${url}" \
      || fail "${label} shared-source remote configuration failed."
  fi
  git --git-dir="${mirror}" fetch -q --depth 1 origin \
    "${revision}:refs/iproteinstudio/${revision}" \
    || fail "${label} pinned revision download failed."
  git init -q "${stage}" || fail "${label} shared source checkout failed."
  mkdir -p "${stage}/.git/objects/info"
  (cd "${mirror}/objects" && pwd -P) > "${stage}/.git/objects/info/alternates" \
    || fail "${label} shared object-store link failed."
  git -C "${stage}" remote add origin "${url}" \
    || fail "${label} source remote configuration failed."
  git -C "${stage}" checkout -q --detach "${revision}" \
    || fail "${label} pinned revision checkout failed."
  actual="$(git -C "${stage}" rev-parse HEAD 2>/dev/null)" \
    || fail "Could not identify the staged ${label} revision."
  [[ "${actual}" == "${revision}" ]] \
    || fail "Staged ${label} revision ${actual} did not match ${revision}."

  if [[ -e "${target}" || -L "${target}" ]]; then
    backup_root="${NANOHUNTER_ROOT}/backups/sources"
    backup="${backup_root}/$(basename "${target}")-$(date -u +%Y%m%dT%H%M%SZ)-$$"
    mkdir -p "${backup_root}"
    mv "${target}" "${backup}" \
      || fail "Could not preserve the previous ${label} source before update."
    echo "  retained recoverable previous ${label} source at ${backup}"
  fi
  mv "${stage}" "${target}" || fail "Could not activate the pinned ${label} source."
}

uv_install_locked() {
  local python="$1" lock="$2"; shift 2
  [[ -x "${UV_BIN}" ]] || fail "Pinned uv is missing: ${UV_BIN}"
  "${UV_BIN}" pip install --python "${python}" --link-mode clone \
    --require-hashes "$@" -r "${lock}" >/dev/null
}

uv_install_editable() {
  local python="$1" source="$2"
  "${UV_BIN}" pip install --python "${python}" --link-mode clone \
    --no-deps --no-build-isolation -e "${source}" >/dev/null
}

assert_runtime_idle() {
  if command -v pgrep >/dev/null 2>&1 \
     && pgrep -f "${NANOHUNTER_ROOT}/venvs/" >/dev/null 2>&1; then
    fail "A Studio prediction or design process is using the managed runtime. Let it finish before installing or updating engines."
  fi
}

check_sha256() {
  local file="$1" expected="$2" actual
  [[ -f "${file}" ]] || return 1
  actual="$(shasum -a 256 "${file}" | awk '{print $1}')" || return 1
  [[ "${actual}" == "${expected}" ]]
}

rfd3_ema_weights_current() {
  [[ -f "${RFD3_ROOT}/rfd3_weight_set.py" \
     && -f "${RFD3_WEIGHTS_PATH}" ]] || return 1
  python3 "${RFD3_ROOT}/rfd3_weight_set.py" \
    --check-artifact "${RFD3_WEIGHTS_PATH}" >/dev/null 2>&1
}

# ---------------------------------------------------------------- detection --

constraint_runtime_current() {
  [[ -x "${PROTENIX_CONSTRAINT_VENV}/bin/protenix" \
     && -d "${PROTENIX_CONSTRAINT_REPO}" \
     && -f "${PROTENIX_CONSTRAINT_MODEL_DIR}/checkpoint/protenix_base_constraint_v0.5.0.pt" \
     && -f "${PROTENIX_CONSTRAINT_MODEL_DIR}/common/components.cif" \
     && -f "${PROTENIX_CONSTRAINT_MODEL_DIR}/common/components.cif.rdkit_mol.pkl" \
     && -f "${PROTENIX_CONSTRAINT_MODEL_DIR}/install_receipt.json" \
     && -f "${PROTENIX_CONSTRAINT_PATCH}" \
     && -f "${PROTENIX_CONSTRAINT_ZERO_SUBSTRUCTURE_PATCH}" ]] || return 1
  python3 - "${PROTENIX_CONSTRAINT_MODEL_DIR}/install_receipt.json" \
    "${PROTENIX_CONSTRAINT_PATCH}" "${PROTENIX_CONSTRAINT_ZERO_SUBSTRUCTURE_PATCH}" \
    "${PROTENIX_CONSTRAINT_REPO}/protenix/model/modules/embedders.py" <<'PY'
import hashlib, json, pathlib, sys
receipt, base_patch, zero_patch, source = map(pathlib.Path, sys.argv[1:])
try:
    data = json.loads(receipt.read_text())
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
if data.get("patch_sha256") != digest(base_patch):
    raise SystemExit(1)
if data.get("zero_substructure_patch_sha256") != digest(zero_patch):
    raise SystemExit(1)
if not source.is_file() or data.get("substructure_source_sha256") != digest(source):
    raise SystemExit(1)
PY
}

detect() {
  if [[ -x "${BOLTZ_VENV}/bin/python" \
     && -f "${BOLTZ_MODEL_DIR}/boltz2_conf.ckpt" \
     && -d "${BOLTZ_MODEL_DIR}/mols" ]]; then
    state boltz ok "Boltz-2 structure environment with managed model and CCD data"
  else
    state_absent_or_partial boltz "environment, structure weights, or CCD data absent" \
      "${BOLTZ_VENV}" "${BOLTZ_MODEL_DIR}"
  fi
  [[ -f "${BOLTZ_MODEL_DIR}/boltz2_aff.ckpt" ]] \
    && state boltz_affinity ok "optional small-molecule affinity checkpoint" \
    || state_absent_or_partial boltz_affinity "optional affinity checkpoint absent" \
         "${BOLTZ_MODEL_DIR}/boltz2_aff.ckpt"
  [[ -x "${LIGAND_VENV}/bin/python" \
     && -f "${LIGANDMPNN_REPO}/run.py" \
     && -f "${LIGANDMPNN_REPO}/model_params/proteinmpnn_v_48_020.pt" \
     && -f "${LIGANDMPNN_REPO}/model_params/solublempnn_v_48_020.pt" \
     && -f "${LIGANDMPNN_REPO}/model_params/ligandmpnn_v_32_010_25.pt" \
     && -f "${LIGANDMPNN_REPO}/model_params/abmpnn.pt" ]] \
    && state mpnn ok "ProteinMPNN / SolubleMPNN / LigandMPNN / AbMPNN" \
    || state_absent_or_partial mpnn "environment or source is incomplete" "${LIGAND_VENV}" "${LIGANDMPNN_REPO}"
  [[ -x "${ANTIFOLD_VENV}/bin/python" && -d "${ANTIFOLD_REPO}" \
     && -f "${ANTIFOLD_REPO}/models/model.pt" ]] && state antifold ok "AntiFold" \
    || state_absent_or_partial antifold "environment or source is incomplete" "${ANTIFOLD_VENV}" "${ANTIFOLD_REPO}"
  if [[ -x "${INTELLIFOLD_VENV}/bin/python" \
     && -f "${INTELLIFOLD_MODEL_DIR}/intellifold_v2_flash.pt" \
     && -f "${INTELLIFOLD_MODEL_DIR}/ccd_v2.pkl" ]]; then
    state intellifold ok "IntelliFold PyTorch/MPS with v2 Flash weights"
  else
    state_absent_or_partial intellifold "environment, v2 Flash weights, or CCD absent" \
      "${INTELLIFOLD_VENV}" "${INTELLIFOLD_REPO}" "${INTELLIFOLD_MODEL_DIR}"
  fi
  [[ -f "${INTELLIFOLD_MODEL_DIR}/intellifold_v2.pt" ]] \
    && state intellifold_full ok "optional IntelliFold full-v2 checkpoint" \
    || state_absent_or_partial intellifold_full "optional full-v2 checkpoint absent" \
         "${INTELLIFOLD_MODEL_DIR}/intellifold_v2.pt"
  if [[ -x "${PROTENIX_VENV}/bin/protenix" \
     && -f "${PROTENIX_MODEL_DIR}/common/components.cif" \
     && -f "${PROTENIX_MODEL_DIR}/common/components.cif.rdkit_mol.pkl" ]]; then
    state protenix ok "shared native-MPS runtime and chemical data"
  else
    state_absent_or_partial protenix "runtime or shared chemical data absent" \
      "${PROTENIX_VENV}" "${PROTENIX_REPO}" "${PROTENIX_MODEL_DIR}"
  fi
  [[ -f "${PROTENIX_MODEL_DIR}/checkpoint/protenix-v2.pt" ]] \
    && state protenix_v2 ok "Protenix v2 checkpoint" \
    || state_absent_or_partial protenix_v2 "Protenix v2 checkpoint absent" \
         "${PROTENIX_MODEL_DIR}/checkpoint/protenix-v2.pt"
  [[ -f "${PROTENIX_MODEL_DIR}/checkpoint/protenix_mini_default_v0.5.0.pt" ]] \
    && state protenix_mini ok "Protenix Mini checkpoint" \
    || state_absent_or_partial protenix_mini "Protenix Mini checkpoint absent" \
         "${PROTENIX_MODEL_DIR}/checkpoint/protenix_mini_default_v0.5.0.pt"
  if constraint_runtime_current; then
    state protenix_constraint ok "Protenix Constraint v0.5 (native MPS, strict ESM-free profile)"
  elif [[ -x "${PROTENIX_CONSTRAINT_VENV}/bin/protenix" \
       && -f "${PROTENIX_CONSTRAINT_MODEL_DIR}/checkpoint/protenix_base_constraint_v0.5.0.pt" ]]; then
    state protenix_constraint update "installed checkpoint is reusable; runtime contract or patch needs updating"
  else
    state_absent_or_partial protenix_constraint "install incomplete; valid checkpoint files are reused on retry" \
      "${PROTENIX_CONSTRAINT_VENV}" "${PROTENIX_CONSTRAINT_REPO}" "${PROTENIX_CONSTRAINT_MODEL_DIR}"
  fi
  if [[ -x "${OPENFOLD_VENV}/bin/python" && -f "${OPENFOLD_CHECKPOINT_PATH}" ]]; then
    state openfold3 ok "OpenFold-3-MLX with checkpoint"
  else
    state_absent_or_partial openfold3 "environment or checkpoint absent" \
      "${OPENFOLD_VENV}" "${OPENFOLD_REPO}" "${OPENFOLD_MODEL_DIR}"
  fi
  # LASErMPNN is ligand-aware inverse folding, used by both design tabs for
  # small-molecule targets. It has no MPS build, so it runs on CPU.
  if [[ -x "${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_lasermpnn/bin/python" \
     && -f "${NANOHUNTER_ROOT}/src/LASErMPNN/model_weights/laser_weights_0p1A_nothing_heldout.pt" ]] \
     && (cd "${SRC_DIR}" && "${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_lasermpnn/bin/python" -c \
       "import LASErMPNN.run_batch_inference; from torch_cluster import knn_graph; from torch_scatter import scatter" \
       >/dev/null 2>&1); then
    state lasermpnn ok "LASErMPNN"
  else
    state_absent_or_partial lasermpnn "environment, source, weights, or compiled extensions absent" \
      "${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_lasermpnn" "${NANOHUNTER_ROOT}/src/LASErMPNN"
  fi
  if [[ -x "${RFD3_ROOT}/.venv/bin/python" ]]; then
    # Installation and `install_rfd3.sh --check` verify both multi-GB hashes.
    # Do not re-read them on every app launch merely to populate the Engines
    # sheet; that makes detection take many seconds on an otherwise ready app.
    if [[ -f "${RFD3_CHECKPOINT_PATH}" && -f "${RFD3_WEIGHTS_PATH}" ]] \
       && rfd3_ema_weights_current; then
      if [[ -f "${RECEIPTS_DIR}/rfd3.json" ]]; then
        state rfd3 ok "RFdiffusion3 MLX with checkpoint and verified EMA weights"
      else
        state rfd3 update "engine is usable; installation provenance still needs finalizing"
      fi
    elif [[ -f "${RFD3_CHECKPOINT_PATH}" && -f "${RFD3_WEIGHTS_PATH}" ]]; then
      state rfd3 update "exported weights are not verified EMA shadow weights; repair RFdiffusion3 before use"
    else
      state rfd3 incomplete "checkpoint or exported MLX weights absent"
    fi
  else
    state_absent_or_partial rfd3 "environment, checkpoint, or exported weights absent" "${RFD3_ROOT}"
  fi
}

if [[ "${DETECT_ONLY}" -eq 1 ]]; then
  detect
  echo "NHDONE|ok"
  exit 0
fi

acquire_install_lock
assert_runtime_idle

if [[ "${MINIMIZE_STORAGE}" -eq 1 ]]; then
  step minimize 10 "Consolidating verified duplicate engine assets"
  [[ -f "${MANAGED_STORAGE}" ]] \
    || fail "Bundled managed-storage helper is missing."
  result="$(python3 "${MANAGED_STORAGE}" --root "${NANOHUNTER_ROOT}")" \
    || fail "Managed-storage consolidation failed without changing unverified data."
  echo "  ${result}"
  detect
  step done 100 "Verified duplicate engine assets consolidated"
  echo "NHDONE|ok"
  exit 0
fi

# ------------------------------------------------------------------- reuse ---
# On a machine that already has NanoHunter installed, symlinking its venvs/,
# src/ and models/ avoids duplicating tens of gigabytes. The app keeps using its
# own vendored runner and examples, so the pinned pipeline version still applies
# -- only the heavy installed environments are shared.

# RFD3 links independently of NanoHunter: the two are separate checkouts with
# separate environments, and a user may well have one without the other.
link_rfd3() {
  local target="$1"
  [[ -d "${target}" ]] || fail "No such directory: ${target}"
  [[ -f "${target}/install_rfd3.sh" ]] \
    || fail "${target} does not look like an RFD3 checkout (no install_rfd3.sh)."
  if [[ -L "${RFD3_ROOT}" ]]; then
    rm -f "${RFD3_ROOT}"
  elif [[ -d "${RFD3_ROOT}" ]]; then
    mv "${RFD3_ROOT}" "${RFD3_ROOT}.replaced-$(date -u +%Y%m%d%H%M%S)" \
      || fail "Could not move aside existing ${RFD3_ROOT}"
  fi
  ln -s "${target}" "${RFD3_ROOT}" || fail "Could not link ${RFD3_ROOT} -> ${target}"
  echo "  rfd3 -> ${target}"
  state link_rfd3 ok "${target}"
}

if [[ -n "${LINK_RFD3}" && -z "${LINK_EXISTING}" ]]; then
  step link 5 "Linking to your existing RFdiffusion3 installation"
  link_rfd3 "${LINK_RFD3}"
  detect
  step done 100 "Linked to existing RFdiffusion3"
  echo "NHDONE|ok"
  exit 0
fi

# Link *individual* components rather than whole directories.
#
# Symlinking venvs/, src/ and models/ wholesale would hide an installation the
# app already has -- on a machine where the app installed its own Boltz and
# IntelliFold months ago, replacing the directory means those working
# environments disappear behind the link, and the aside-moved copy wastes
# gigabytes. Linking one venv / repo / model directory at a time adds only what
# is genuinely missing and never touches what already works.
link_component() {
  local rel="$1"
  local target="${LINK_EXISTING}/${rel}"
  local link="${NANOHUNTER_ROOT}/${rel}"
  [[ -e "${target}" ]] || return 1
  if [[ -L "${link}" ]]; then
    # An existing link is ours: repoint it, it costs nothing.
    rm -f "${link}"
  elif [[ -e "${link}" ]]; then
    echo "  keep      ${rel} (already installed here)"
    return 0
  fi
  mkdir -p "$(dirname "${link}")"
  ln -s "${target}" "${link}" || fail "Could not link ${link} -> ${target}"
  echo "  link      ${rel}"
  return 0
}

if [[ -n "${LINK_EXISTING}" ]]; then
  step link 5 "Adding the engines you already have"
  [[ -d "${LINK_EXISTING}" ]] || fail "No such directory: ${LINK_EXISTING}"
  [[ -x "${LINK_EXISTING}/venvs/${VENV_PREFIX}_boltz/bin/python" ]] \
    || fail "${LINK_EXISTING} does not look like an installed NanoHunter (no Boltz venv)."

  mkdir -p "${NANOHUNTER_ROOT}"/{venvs,src,models}
  for rel in \
    "venvs/${VENV_PREFIX}_boltz" \
    "venvs/${VENV_PREFIX}_ligandmpnn" \
    "venvs/${VENV_PREFIX}_antifold" \
    "venvs/${VENV_PREFIX}_intellifold" \
    "venvs/${VENV_PREFIX}_protenix" \
    "venvs/${VENV_PREFIX}_protenix_constraint" \
    "venvs/${VENV_PREFIX}_openfold3_mlx" \
    "venvs/${VENV_PREFIX}_lasermpnn" \
    "src/LigandMPNN" "src/AntiFold" "src/IntelliFold" "src/Protenix" \
    "src/ProtenixConstraint" \
    "src/openfold-3-mlx" "src/LASErMPNN" \
    "models/boltz2" "models/intellifold" "models/protenix" \
    "models/protenix_constraint" "models/openfold3"
  do
    link_component "${rel}" || echo "  absent    ${rel} (not in ${LINK_EXISTING})"
  done

  state link ok "${LINK_EXISTING}"
  [[ -n "${LINK_RFD3}" ]] && link_rfd3 "${LINK_RFD3}"
  detect
  step done 100 "Added everything available from your existing installation"
  echo "NHDONE|ok"
  exit 0
fi

# ---------------------------------------------------------- materialisation ---
#
# Replace symlinked components with real local copies, so the installation is
# self-contained and reproducible rather than depending on another checkout
# staying where it is. Copies first and swaps afterwards, so an interrupted run
# leaves the working symlink in place rather than a half-copied directory.

relocate_venv() {
  local venv="${1%/}"
  local name; name="$(basename "${venv}")"
  local script old_root

  # Console scripts come in two shapes: a plain "#!<venv>/bin/python" shebang,
  # and a two-line /bin/sh wrapper that execs the interpreter on line 2. Only
  # rewriting line 1 fixes the first and silently leaves the second pointing at
  # the old location, so both are handled by replacing the old root wherever it
  # appears in a wrapper.
  old_root=""
  for script in "${venv}"/bin/*; do
    [[ -f "${script}" ]] || continue
    case "$(basename "${script}")" in
      activate|activate.*|*.sh) ;;
      *) [[ "$(head -c 2 "${script}" 2>/dev/null)" == "#!" ]] || continue ;;
    esac
    local found
    # Derive the environment root from its interpreter path. This works for
    # both the main <root>/venvs/<name> layout and RFdiffusion3's
    # <root>/rfd3/.venv layout.
    found="$(LC_ALL=C grep -Eo "/[^\"']*/bin/python[0-9.]*" "${script}" 2>/dev/null \
      | head -n 1 | sed -E 's|/bin/python[0-9.]*$||' || true)"
    if [[ -n "${found}" && "${found}" != "${venv}" ]]; then old_root="${found}"; break; fi
  done
  [[ -n "${old_root}" ]] || return 0

  local rewritten=0
  for script in "${venv}"/bin/*; do
    [[ -f "${script}" ]] || continue
    # Text wrappers only, never a binary that happens to contain the bytes.
    # activate/activate.csh/activate.fish start with "# ", not "#!", and are
    # sourced by the runner -- a stale one silently re-points VIRTUAL_ENV and
    # PATH back at the old location, so they have to be included.
    case "$(basename "${script}")" in
      activate|activate.*|*.sh) ;;
      *) [[ "$(head -c 2 "${script}" 2>/dev/null)" == "#!" ]] || continue ;;
    esac
    if LC_ALL=C grep -q "${old_root}" "${script}" 2>/dev/null; then
      LC_ALL=C sed -i '' "s|${old_root}|${venv}|g" "${script}" 2>/dev/null && rewritten=$((rewritten+1))
    fi
  done
  if [[ -f "${venv}/pyvenv.cfg" ]]; then
    LC_ALL=C sed -i '' "s|${old_root}|${venv}|g" "${venv}/pyvenv.cfg" 2>/dev/null || true
  fi
  [[ "${rewritten}" -eq 0 ]] || echo "  relocated ${rewritten} script(s) in ${name}"
}

# Editable installs (`pip install -e`) record the *source* directory as an
# absolute path in site-packages. Copying the venv does not move that pointer, so
# the copy keeps importing the original checkout -- an installation that looks
# self-contained and silently is not, and that breaks the moment the original is
# deleted. This re-points them at this installation's own src/.
relocate_editables() {
  # Editable installs (`pip install -e`) record the *source* directory as an
  # absolute path inside site-packages -- in a .pth, and in a generated
  # __editable___*_finder.py. Copying or moving a venv does not move those, so
  # the environment keeps importing from wherever it came from: an installation
  # that looks self-contained and silently is not, and that breaks outright once
  # the original is gone.
  #
  # Done in Python rather than shell because it has to find the stale root by
  # inspection (a repair after a move has no record of the old path) and rewrite
  # several file types; the shell version failed silently, which is exactly the
  # failure mode this whole function exists to prevent.
  local venv="${1%/}" old_root="${2:-}" new_root="$3"
  "${PYTHON_BIN:-python3}" - "${venv}" "${old_root}" "${new_root}" <<'PYEOF'
import os, re, sys
venv, old_root, new_root = sys.argv[1], sys.argv[2], sys.argv[3]
targets = []
for base, _dirs, files in os.walk(venv):
    parts = base.split(os.sep)
    if "site-packages" not in parts:
        continue
    for name in files:
        at_site_root = os.path.basename(base) == "site-packages"
        if (at_site_root and (name.endswith((".pth", ".egg-link"))
                              or name.startswith("__editable__"))) \
                or name == "direct_url.json":
            targets.append(os.path.join(base, name))

if not old_root:
    probe = re.compile(r"(/[\w./ -]+)/src/[\w.-]+")
    for path in targets:
        try:
            text = open(path, errors="replace").read()
        except OSError:
            continue
        # direct_url.json stores editable sources as file:///absolute/path;
        # strip the URI prefix before extracting the filesystem root so the
        # captured value is /Users/... rather than ///Users/....
        match = probe.search(text.replace("file://", ""))
        if match and match.group(1) != new_root:
            old_root = match.group(1)
            break

if not old_root or old_root == new_root:
    raise SystemExit(0)

changed = 0
for path in targets:
    try:
        text = open(path, errors="replace").read()
    except OSError:
        continue
    if old_root not in text:
        continue
    try:
        open(path, "w").write(text.replace(old_root, new_root))
        changed += 1
    except OSError:
        pass
if changed:
    print(f"  re-pointed {changed} editable install file(s) in {os.path.basename(venv)}")
PYEOF
}

materialise_component() {
  local rel="$1"
  local link="${NANOHUNTER_ROOT}/${rel}"
  [[ -L "${link}" ]] || return 0
  local target
  target="$(readlink "${link}")"
  [[ -e "${target}" ]] || { echo "  BROKEN    ${rel} -> ${target}"; return 1; }

  local staging="${link}.materialising"
  rm -rf "${staging}"
  mkdir -p "$(dirname "${staging}")"

  # RFdiffusion3 checkouts carry campaign outputs and cached fixtures that can
  # run to gigabytes and belong to whoever produced them, not to this
  # installation. Copy the code, environment and weights; leave the results.
  local -a excludes=()
  if [[ "${rel}" == "rfd3" ]]; then
    excludes=(--exclude campaigns --exclude .git --exclude 'oracle/*.npz'
              --exclude 'oracle/out' --exclude benchmarks --exclude figures)
  fi

  # -a preserves symlinks *inside* a venv (its python is one) and permissions.
  # ${arr[@]+...} guards an empty array: with `set -u`, bash 3.2 on macOS treats
  # "${arr[@]}" on an empty array as unbound rather than as no arguments.
  if rsync -a ${excludes[@]+"${excludes[@]}"} "${target}/" "${staging}/" 2>/dev/null \
     || cp -a "${target}/" "${staging}/" 2>/dev/null; then
    rm -f "${link}"
    mv "${staging}" "${link}" || { echo "  FAILED    ${rel}"; return 1; }
    echo "  copied    ${rel}"
  else
    rm -rf "${staging}"
    echo "  FAILED    ${rel} (copy error)"
    return 1
  fi
}

if [[ "${REPAIR_VENVS}" -eq 1 ]]; then
  step repair 10 "Re-pointing environments after a move"
  for venv in "${NANOHUNTER_ROOT}"/venvs/*/ "${NANOHUNTER_ROOT}"/rfd3/.venv/; do
    [[ -d "${venv}" ]] || continue
    relocate_venv "${venv}"
    relocate_editables "${venv}" "${REPAIR_EDITABLE_SOURCE:-}" "${NANOHUNTER_ROOT}"
  done
  detect
  step done 100 "Environments repaired"
  echo "NHDONE|ok"
  exit 0
fi

if [[ "${MATERIALISE}" -eq 1 ]]; then
  step materialise 5 "Making this installation self-contained"
  failed=0
  # Remember where the components came from, so editable installs pointing back
  # at that checkout can be re-pointed once the copies are in place.
  MATERIALISE_SOURCE=""
  for probe in \
    "venvs/${VENV_PREFIX}_protenix_constraint" "src/ProtenixConstraint" \
    "venvs/${VENV_PREFIX}_openfold3_mlx" "src/openfold-3-mlx" \
    "venvs/${VENV_PREFIX}_protenix" "src/Protenix" \
    "venvs/${VENV_PREFIX}_intellifold" "src/IntelliFold"
  do
    if [[ -L "${NANOHUNTER_ROOT}/${probe}" ]]; then
      MATERIALISE_SOURCE="$(readlink "${NANOHUNTER_ROOT}/${probe}")"
      MATERIALISE_SOURCE="${MATERIALISE_SOURCE%/${probe}}"
      break
    fi
  done
  for rel in \
    "venvs/${VENV_PREFIX}_boltz" "venvs/${VENV_PREFIX}_ligandmpnn" \
    "venvs/${VENV_PREFIX}_antifold" "venvs/${VENV_PREFIX}_intellifold" \
    "venvs/${VENV_PREFIX}_protenix" \
    "venvs/${VENV_PREFIX}_protenix_constraint" \
    "venvs/${VENV_PREFIX}_openfold3_mlx" \
    "venvs/${VENV_PREFIX}_lasermpnn" \
    "src/LigandMPNN" "src/AntiFold" "src/IntelliFold" "src/Protenix" \
    "src/ProtenixConstraint" \
    "src/openfold-3-mlx" "src/LASErMPNN" \
    "models/boltz2" "models/intellifold" "models/protenix" \
    "models/protenix_constraint" "models/openfold3" \
    "rfd3" "venvs" "src" "models"
  do
    materialise_component "${rel}" || failed=1
  done
  # A copied venv still points at where it came from: every console script in
  # bin/ carries a shebang with the *original* absolute path. Left alone the
  # copy would silently keep using the original environment, which defeats the
  # point of making this installation self-contained -- and would break the
  # moment the original was deleted.
  for venv in "${NANOHUNTER_ROOT}"/venvs/*/ "${NANOHUNTER_ROOT}"/rfd3/.venv/; do
    [[ -d "${venv}" ]] || continue
    relocate_venv "${venv}"
    [[ -n "${MATERIALISE_SOURCE}" ]] && relocate_editables "${venv}" "${MATERIALISE_SOURCE}" "${NANOHUNTER_ROOT}"
  done
  detect
  step done 100 "Installation is now self-contained"
  echo "NHDONE|ok"
  [[ "${failed}" -eq 0 ]] || exit 1
  exit 0
fi

# --------------------------------------------------------------- toolchain ---

ensure_uv() {
  if [[ -x "${UV_BIN}" ]] \
     && [[ "$("${UV_BIN}" --version 2>/dev/null | awk '{print $2}')" == "${UV_VERSION}" ]]; then
    return 0
  fi
  command -v curl >/dev/null 2>&1 || fail "curl is required to install the managed Python toolchain."
  local archive stage extracted actual
  mkdir -p "${TOOLCHAIN_DIR}/uv"
  stage="$(mktemp -d "${TOOLCHAIN_DIR}/uv/.uv-${UV_VERSION}.XXXXXX")" \
    || fail "Could not create the uv staging directory."
  archive="${stage}/uv.tar.gz"
  curl --proto '=https' --tlsv1.2 --fail --location --retry 3 \
    --connect-timeout 20 --output "${archive}" \
    "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-aarch64-apple-darwin.tar.gz" \
    || { rm -rf "${stage}"; fail "Could not download pinned uv ${UV_VERSION}."; }
  actual="$(shasum -a 256 "${archive}" | awk '{print $1}')"
  [[ "${actual}" == "${UV_SHA256}" ]] \
    || { rm -rf "${stage}"; fail "Pinned uv archive checksum mismatch; refusing to execute it."; }
  tar -xzf "${archive}" -C "${stage}" \
    || { rm -rf "${stage}"; fail "Could not extract pinned uv ${UV_VERSION}."; }
  extracted="$(find "${stage}" -type f -name uv -perm -111 -print -quit)"
  [[ -n "${extracted}" ]] \
    || { rm -rf "${stage}"; fail "The verified uv archive contained no executable."; }
  mkdir -p "${UV_HOME}"
  cp "${extracted}" "${UV_HOME}/uv.new" || fail "Could not stage the uv executable."
  chmod 755 "${UV_HOME}/uv.new"
  mv -f "${UV_HOME}/uv.new" "${UV_BIN}"
  rm -rf "${stage}"
  [[ "$("${UV_BIN}" --version | awk '{print $2}')" == "${UV_VERSION}" ]] \
    || fail "Managed uv version verification failed."
}

ensure_python() {
  local want="$1" var="$2"
  ensure_uv
  mkdir -p "${UV_PYTHON_INSTALL_DIR}" "${UV_PYTHON_BIN_DIR}" "${UV_CACHE_DIR}" "${PIP_CACHE_DIR}"
  "${UV_BIN}" python install --managed-python "${want}" \
    || fail "Could not install exact managed CPython ${want}."
  local resolved
  resolved="$("${UV_BIN}" python find --managed-python "${want}" 2>/dev/null)" \
    || fail "Could not locate exact managed CPython ${want}."
  case "${resolved}" in
    "${UV_PYTHON_INSTALL_DIR}"/*) ;;
    *) fail "uv resolved Python ${want} outside Studio's managed toolchain: ${resolved}" ;;
  esac
  [[ "$("${resolved}" -c 'import platform; print(platform.python_version())')" == "${want}" ]] \
    || fail "Managed CPython resolved to the wrong patch version (wanted ${want})."
  printf -v "$var" '%s' "${resolved}"
}

download_verified_artifact() {
  local python="$1" output="$2" url="$3" checksum="$4" label="$5"
  local key="$6" start="$7" end="$8"
  [[ -f "${VERIFIED_DOWNLOADER}" ]] || fail "Bundled verified downloader is missing."
  "${python}" "${VERIFIED_DOWNLOADER}" \
    --url "${url}" --sha256 "${checksum}" --output "${output}" \
    --label "${label}" --progress-key "${key}" \
    --progress-start "${start}" --progress-end "${end}" \
    || fail "Could not download or verify ${label}. The partial file was retained for resume."
}

write_component_receipt() {
  local key="$1" version="$2" python="$3" policy="$4"; shift 4
  [[ -f "${COMPONENT_RECEIPT}" ]] || fail "Bundled component receipt helper is missing."
  mkdir -p "${RECEIPTS_DIR}"
  "${python}" "${COMPONENT_RECEIPT}" write \
    --output "${RECEIPTS_DIR}/${key}.json" --component "${key}" \
    --version "${version}" --python "${python}" --device-policy "${policy}" "$@" \
    || fail "Could not verify and record the ${key} installation receipt."
}

begin_versioned_venv() {
  local key="$1" version="$2" final="$3" python="$4"
  TRANSACTION_COMPONENT="${key}"
  TRANSACTION_VERSION="${version}"
  TRANSACTION_FINAL_VENV="${final}"
  TRANSACTION_REUSED=0
  if [[ -x "${final}/bin/python" && -f "${RECEIPTS_DIR}/${key}.json" ]] \
     && python3 "${COMPONENT_RECEIPT}" verify \
          --receipt "${RECEIPTS_DIR}/${key}.json" --packages >/dev/null 2>&1; then
    TRANSACTION_VENV="${final}"
    TRANSACTION_STAGE=""
    TRANSACTION_REUSED=1
    return 0
  fi
  # Receipt creation is deliberately last, after artifact/source/runtime
  # validation. If it alone was interrupted, the atomically committed current
  # environment is still a valid retry candidate. Reuse it only when its
  # transaction marker says ready; the caller repeats health checks and writes
  # a fresh receipt before reporting success.
  if [[ -x "${final}/bin/python" && -L "${final}" ]]; then
    local committed transaction_state transaction_component
    committed="$(cd "$(dirname "${final}")" && cd "$(readlink "${final}")" 2>/dev/null && pwd -P || true)"
    if [[ -n "${committed}" && -f "${committed}/transaction.json" ]]; then
      read -r transaction_state transaction_component < <(python3 - "${committed}/transaction.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(data.get("state", ""), data.get("component", ""))
PY
)
      if [[ "${transaction_state}" == "ready" && "${transaction_component}" == "${key}" ]]; then
        TRANSACTION_VENV="${final}"
        TRANSACTION_STAGE=""
        TRANSACTION_REUSED=1
        echo "  re-validating committed ${key} environment after an interrupted receipt"
        return 0
      fi
    fi
  fi
  [[ -f "${RUNTIME_TRANSACTION}" ]] || fail "Bundled runtime transaction helper is missing."
  TRANSACTION_STAGE="$(python3 "${RUNTIME_TRANSACTION}" prepare \
    --root "${NANOHUNTER_ROOT}" --component "${key}" --version "${version}")" \
    || fail "Could not create the ${key} version staging area."
  TRANSACTION_VENV="${TRANSACTION_STAGE}/venv"
  "${python}" -m venv "${TRANSACTION_VENV}" \
    || fail "Could not stage the ${key} Python environment."
}

commit_versioned_venv() {
  [[ "${TRANSACTION_REUSED}" -eq 0 ]] || return 0
  python3 "${RUNTIME_TRANSACTION}" commit \
    --root "${NANOHUNTER_ROOT}" --component "${TRANSACTION_COMPONENT}" \
    --version "${TRANSACTION_VERSION}" --stage "${TRANSACTION_STAGE}" \
    --mapping "${TRANSACTION_FINAL_VENV}=venv" >/dev/null \
    || fail "Could not atomically activate the verified ${TRANSACTION_COMPONENT} environment."
  relocate_venv "${TRANSACTION_FINAL_VENV}"
}

seed_shared_protenix_common() {
  local model_dir="$1" source name expected
  source="${model_dir}/common"
  mkdir -p "${PROTENIX_COMMON_DIR}"
  [[ -d "${source}" && ! -L "${source}" ]] || return 0
  while IFS='|' read -r name expected; do
    [[ -n "${name}" ]] || continue
    if check_sha256 "${source}/${name}" "${expected}" \
       && ! check_sha256 "${PROTENIX_COMMON_DIR}/${name}" "${expected}"; then
      cp -c "${source}/${name}" "${PROTENIX_COMMON_DIR}/${name}" 2>/dev/null \
        || cp "${source}/${name}" "${PROTENIX_COMMON_DIR}/${name}" \
        || fail "Could not migrate existing Protenix common data into shared storage."
    fi
  done <<'EOF'
components.cif|bb31ae5cf6c8bc669924313077cb4231ee5ffefd3a20118cd14f3ec89f8bb6a5
components.cif.rdkit_mol.pkl|d1cfb71f5993a3ebea7c47877022d7f597bbfbaf86e28a4770e957da6c50cd35
obsolete_release_date.csv|a4f3f63ac5d7eebd78b07995cc669b9eccd6f5d8813c9492c9df02868893cf33
clusters-by-entity-40.txt|1ab4af905e75b382eda8dec59917dc3608bee0729e36b9e71baf860bbe86850c
EOF
}

activate_shared_protenix_common() {
  local model_dir="$1" name expected common
  common="${model_dir}/common"
  while IFS='|' read -r name expected; do
    [[ -n "${name}" ]] || continue
    check_sha256 "${PROTENIX_COMMON_DIR}/${name}" "${expected}" \
      || fail "Shared Protenix common-data verification failed: ${name}"
  done <<'EOF'
components.cif|bb31ae5cf6c8bc669924313077cb4231ee5ffefd3a20118cd14f3ec89f8bb6a5
components.cif.rdkit_mol.pkl|d1cfb71f5993a3ebea7c47877022d7f597bbfbaf86e28a4770e957da6c50cd35
obsolete_release_date.csv|a4f3f63ac5d7eebd78b07995cc669b9eccd6f5d8813c9492c9df02868893cf33
clusters-by-entity-40.txt|1ab4af905e75b382eda8dec59917dc3608bee0729e36b9e71baf860bbe86850c
EOF
  if [[ -L "${common}" ]] && [[ "$(readlink "${common}")" == "${PROTENIX_COMMON_DIR}" ]]; then
    return 0
  fi
  local temporary="${model_dir}/.common-link.$$"
  local backup_root="${NANOHUNTER_ROOT}/backups/protenix-common"
  local backup="${backup_root}/$(basename "${model_dir}")-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  mkdir -p "${model_dir}" "${backup_root}"
  ln -s "${PROTENIX_COMMON_DIR}" "${temporary}" \
    || fail "Could not stage the shared Protenix common-data link."
  if [[ -e "${common}" || -L "${common}" ]]; then
    mv "${common}" "${backup}" \
      || { rm -f "${temporary}"; fail "Could not preserve existing Protenix common data."; }
  fi
  if ! mv "${temporary}" "${common}"; then
    [[ -e "${backup}" || -L "${backup}" ]] && mv "${backup}" "${common}"
    fail "Could not activate shared Protenix common data."
  fi
  [[ -e "${backup}" || -L "${backup}" ]] \
    && echo "  retained recoverable pre-migration Protenix data at ${backup}"
}

# A shebang line cannot contain a space: the kernel splits on whitespace, so a
# console script installed under ".../Application Support/..." fails with
# "bad interpreter". Every venv pip creates here would be quietly broken.
case "${NANOHUNTER_ROOT}" in
  *" "*) fail "The install path contains a space (${NANOHUNTER_ROOT}). Python console scripts cannot run from such a path. Use a path without spaces, e.g. ~/.iproteinstudio." ;;
esac

mkdir -p "${NANOHUNTER_ROOT}"/{venvs,src,examples,models,output,numba_cache}

step python 2 "Preparing exact managed Python environments"
command -v git >/dev/null 2>&1 || fail "git not found. Install Xcode Command Line Tools: xcode-select --install"
ensure_python "${PYTHON_311_VERSION}" PYTHON_BIN
if [[ "${WITH_ANTIFOLD}" -eq 1 ]]; then
  ensure_python "${PYTHON_310_VERSION}" ANTIFOLD_PYTHON_BIN
fi
if [[ "${WITH_INTELLIFOLD}" -eq 1 || "${WITH_PROTENIX_CONSTRAINT}" -eq 1 \
   || "${WITH_RFD3}" -eq 1 ]]; then
  ensure_python "${PYTHON_312_VERSION}" INTELLIFOLD_PYTHON_BIN
fi

# ---- Boltz-2 ----
if [[ "${WITH_BOLTZ}" -eq 1 ]]; then
step boltz 8 "Installing Boltz-2"
BOLTZ_FINAL_VENV="${BOLTZ_VENV}"
begin_versioned_venv boltz "${BOLTZ_VERSION}" "${BOLTZ_FINAL_VENV}" "${PYTHON_BIN}"
BOLTZ_VENV="${TRANSACTION_VENV}"
if [[ "${TRANSACTION_REUSED}" -eq 0 ]]; then
  uv_install_locked "${BOLTZ_VENV}/bin/python" "${BOLTZ_LOCK}" \
    || fail "Boltz hash-locked dependency install failed."
fi
mkdir -p "${BOLTZ_MODEL_DIR}"
download_verified_artifact "${BOLTZ_VENV}/bin/python" \
  "${BOLTZ_MODEL_DIR}/boltz2_conf.ckpt" \
  "https://model-gateway.boltz.bio/boltz2_conf.ckpt" \
  "090e82ac8c92f5e943fa1b39e7410a44027bea7243c0bbb3caa67a77fc1428e1" \
  "Boltz-2 structure checkpoint" boltz 8 12
if [[ "${WITH_BOLTZ_AFFINITY}" -eq 1 ]]; then
  download_verified_artifact "${BOLTZ_VENV}/bin/python" \
    "${BOLTZ_MODEL_DIR}/boltz2_aff.ckpt" \
    "https://model-gateway.boltz.bio/boltz2_aff.ckpt" \
    "dcc5cd3722b1c9eaa34267e4ae32f55cbbf1963f4c19319381ccfa30fdd2ca9e" \
    "Boltz-2 affinity checkpoint" boltz_affinity 12 15
  state boltz_affinity ok "optional small-molecule affinity checkpoint"
else
  state boltz_affinity skipped "not requested"
fi
if [[ ! -d "${BOLTZ_MODEL_DIR}/mols" ]]; then
  download_verified_artifact "${BOLTZ_VENV}/bin/python" \
    "${BOLTZ_MODEL_DIR}/mols.tar" \
    "https://huggingface.co/boltz-community/boltz-2/resolve/main/mols.tar" \
    "39e076d96dbec6b4e86982bbda16f3a53a2a60c9bdc17828d88f6f9a0c7d1fd7" \
    "Boltz-2 chemical-component archive" boltz 15 21
fi
"${BOLTZ_VENV}/bin/python" - "${BOLTZ_MODEL_DIR}" <<'PY' \
  || fail "Boltz-2 model or CCD download failed."
import hashlib
import os
import shutil
import sys
import tarfile
from pathlib import Path

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()

# Extract only after the archive has passed its checksum. Refuse path traversal
# rather than trusting a remote tarball with the managed installation root.
mols = root / "mols"
if not mols.is_dir():
    archive_path = root / "mols.tar"
    archive_sha = "39e076d96dbec6b4e86982bbda16f3a53a2a60c9bdc17828d88f6f9a0c7d1fd7"
    if not archive_path.is_file() or digest(archive_path) != archive_sha:
        raise RuntimeError("verified Boltz-2 chemical-component archive is missing")
    stage = root / ".mols-extract"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            resolved = (stage / member.name).resolve()
            if stage.resolve() not in resolved.parents and resolved != stage.resolve():
                raise RuntimeError(f"unsafe path in Boltz CCD archive: {member.name}")
        archive.extractall(stage)
    extracted = stage / "mols"
    if not extracted.is_dir():
        raise RuntimeError("Boltz CCD archive contained no mols directory")
    os.replace(extracted, mols)
    shutil.rmtree(stage, ignore_errors=True)
    archive_path.unlink()
else:
    # Older setup builds retained this 1.7 GB archive after extraction. It is a
    # reproducible download, not a runtime input, so do not charge every user
    # twice for the same CCD data.
    (root / "mols.tar").unlink(missing_ok=True)
PY
"${BOLTZ_VENV}/bin/python" -c \
  'import boltz, torch; assert torch.backends.mps.is_available()' >/dev/null \
  || fail "Boltz-2 staged runtime failed its Apple-GPU import check."
commit_versioned_venv
BOLTZ_VENV="${BOLTZ_FINAL_VENV}"
write_component_receipt boltz "${BOLTZ_VERSION}" "${BOLTZ_VENV}/bin/python" \
  "native-mps-preferred" --lock "${BOLTZ_LOCK}" \
  --artifact "${BOLTZ_MODEL_DIR}/boltz2_conf.ckpt=090e82ac8c92f5e943fa1b39e7410a44027bea7243c0bbb3caa67a77fc1428e1" \
  --metadata "ccd_archive_sha256=39e076d96dbec6b4e86982bbda16f3a53a2a60c9bdc17828d88f6f9a0c7d1fd7"
if [[ "${WITH_BOLTZ_AFFINITY}" -eq 1 ]]; then
  write_component_receipt boltz_affinity "${BOLTZ_VERSION}" "${BOLTZ_VENV}/bin/python" \
    "native-mps-preferred" \
    --artifact "${BOLTZ_MODEL_DIR}/boltz2_aff.ckpt=dcc5cd3722b1c9eaa34267e4ae32f55cbbf1963f4c19319381ccfa30fdd2ca9e"
fi
state boltz ok "Boltz-2 structure prediction"
else
  state boltz skipped "not requested"
  state boltz_affinity skipped "not requested"
fi

# ---- LigandMPNN family (+ AbMPNN weights) ----
step ligandmpnn 22 "Installing sequence designers (ProteinMPNN / SolubleMPNN / LigandMPNN / AbMPNN)"
LIGAND_FINAL_VENV="${LIGAND_VENV}"
begin_versioned_venv mpnn "${LIGANDMPNN_REV}" "${LIGAND_FINAL_VENV}" "${PYTHON_BIN}"
LIGAND_VENV="${TRANSACTION_VENV}"
ensure_pinned_repo "LigandMPNN" "https://github.com/dauparas/LigandMPNN.git" \
  "${LIGANDMPNN_REV}" "${LIGANDMPNN_REPO}"
if [[ "${TRANSACTION_REUSED}" -eq 0 ]]; then
  uv_install_locked "${LIGAND_VENV}/bin/python" "${MPNN_LOCK}" \
    || fail "Sequence-designer hash-locked dependency install failed."
fi
MODEL_DIR="${LIGANDMPNN_REPO}/model_params"; mkdir -p "${MODEL_DIR}"
step weights 32 "Downloading designer weights"
download_verified_artifact "${LIGAND_VENV}/bin/python" \
  "${MODEL_DIR}/proteinmpnn_v_48_020.pt" \
  "https://files.ipd.uw.edu/pub/ligandmpnn/proteinmpnn_v_48_020.pt" \
  "c9cb4a671d79604111231f8dbfc7c590e06f1197453b7a6854ac6661a642f5bd" \
  "ProteinMPNN checkpoint" mpnn 32 35
download_verified_artifact "${LIGAND_VENV}/bin/python" \
  "${MODEL_DIR}/solublempnn_v_48_020.pt" \
  "https://files.ipd.uw.edu/pub/ligandmpnn/solublempnn_v_48_020.pt" \
  "7af52d090172c230c7f0e9d21e02203f6b3a38b16db58d3c7a3960e0a9a6e31a" \
  "SolubleMPNN checkpoint" mpnn 35 38
download_verified_artifact "${LIGAND_VENV}/bin/python" \
  "${MODEL_DIR}/ligandmpnn_v_32_010_25.pt" \
  "https://files.ipd.uw.edu/pub/ligandmpnn/ligandmpnn_v_32_010_25.pt" \
  "161cd264061fda9680cbb940255522ae42f2966c552d045d87913d9452a80970" \
  "LigandMPNN checkpoint" mpnn 38 41
download_verified_artifact "${LIGAND_VENV}/bin/python" \
  "${MODEL_DIR}/abmpnn.pt" \
  "https://zenodo.org/records/8164693/files/abmpnn.pt?download=1" \
  "fd41b40ee0f51974d73e1acb754cd8acaa36b3327543d5d28bcf4aa4e07b4a1b" \
  "AbMPNN checkpoint" mpnn 41 44
"${LIGAND_VENV}/bin/python" -c 'import torch, numpy' >/dev/null \
  || fail "Sequence-designer staged runtime failed its import check."
commit_versioned_venv
LIGAND_VENV="${LIGAND_FINAL_VENV}"
write_component_receipt mpnn "${LIGANDMPNN_REV}" "${LIGAND_VENV}/bin/python" \
  "native-mps-when-supported" --lock "${MPNN_LOCK}" \
  --source "${LIGANDMPNN_REPO}=${LIGANDMPNN_REV}" \
  --artifact "${MODEL_DIR}/proteinmpnn_v_48_020.pt=c9cb4a671d79604111231f8dbfc7c590e06f1197453b7a6854ac6661a642f5bd" \
  --artifact "${MODEL_DIR}/solublempnn_v_48_020.pt=7af52d090172c230c7f0e9d21e02203f6b3a38b16db58d3c7a3960e0a9a6e31a" \
  --artifact "${MODEL_DIR}/ligandmpnn_v_32_010_25.pt=161cd264061fda9680cbb940255522ae42f2966c552d045d87913d9452a80970" \
  --artifact "${MODEL_DIR}/abmpnn.pt=fd41b40ee0f51974d73e1acb754cd8acaa36b3327543d5d28bcf4aa4e07b4a1b"
state mpnn ok "ProteinMPNN / SolubleMPNN / LigandMPNN / AbMPNN"

# ---- AntiFold ----
if [[ "${WITH_ANTIFOLD}" -eq 1 ]]; then
step antifold 45 "Installing AntiFold (antibody-aware designer)"
ensure_pinned_repo "AntiFold" "https://github.com/oxpig/AntiFold.git" \
  "${ANTIFOLD_REV}" "${ANTIFOLD_REPO}"
ANTIFOLD_FINAL_VENV="${ANTIFOLD_VENV}"
begin_versioned_venv antifold "${ANTIFOLD_REV}" "${ANTIFOLD_FINAL_VENV}" "${ANTIFOLD_PYTHON_BIN}"
ANTIFOLD_VENV="${TRANSACTION_VENV}"
if [[ "${TRANSACTION_REUSED}" -eq 0 ]]; then
  uv_install_locked "${ANTIFOLD_VENV}/bin/python" "${ANTIFOLD_LOCK}" \
    || fail "AntiFold hash-locked dependency install failed."
  uv_install_editable "${ANTIFOLD_VENV}/bin/python" "${ANTIFOLD_REPO}" \
    || fail "AntiFold install failed."
fi
ANTIFOLD_MODEL_PATH="${ANTIFOLD_REPO}/models/model.pt"
download_verified_artifact "${ANTIFOLD_VENV}/bin/python" \
  "${ANTIFOLD_MODEL_PATH}" \
  "https://opig.stats.ox.ac.uk/data/downloads/AntiFold/models/model.pt" \
  "d5c442fa0372c28f4d0026d2f551b6f8ba7e7a127cb6837813a88093ed233e9e" \
  "AntiFold checkpoint" antifold 45 59
"${ANTIFOLD_VENV}/bin/python" -c 'import antifold, torch' >/dev/null \
  || fail "AntiFold staged runtime failed its import check."
commit_versioned_venv
ANTIFOLD_VENV="${ANTIFOLD_FINAL_VENV}"
write_component_receipt antifold "${ANTIFOLD_REV}" "${ANTIFOLD_VENV}/bin/python" \
  "native-mps-when-supported" --lock "${ANTIFOLD_LOCK}" \
  --source "${ANTIFOLD_REPO}=${ANTIFOLD_REV}" \
  --artifact "${ANTIFOLD_MODEL_PATH}=d5c442fa0372c28f4d0026d2f551b6f8ba7e7a127cb6837813a88093ed233e9e"
state antifold ok "AntiFold"
else
  state antifold skipped "not requested"
fi

# ---- IntelliFold (PyTorch) ----
if [[ "${WITH_INTELLIFOLD}" -eq 1 ]]; then
step intellifold 60 "Installing IntelliFold prediction engine"
ensure_pinned_repo "IntelliFold" "https://github.com/IntelliGen-AI/IntelliFold.git" \
  "${INTELLIFOLD_REV}" "${INTELLIFOLD_REPO}"
[[ -f "${INTELLIFOLD_STUDIO_PATCH}" ]] \
  || fail "Bundled IntelliFold PyTorch/MPS patch is missing: ${INTELLIFOLD_STUDIO_PATCH}"
if git -C "${INTELLIFOLD_REPO}" apply --check "${INTELLIFOLD_STUDIO_PATCH}" >/dev/null 2>&1; then
  git -C "${INTELLIFOLD_REPO}" apply "${INTELLIFOLD_STUDIO_PATCH}" \
    || fail "Could not apply the validated IntelliFold PyTorch/MPS patch."
elif git -C "${INTELLIFOLD_REPO}" apply --reverse --check "${INTELLIFOLD_STUDIO_PATCH}" >/dev/null 2>&1; then
  echo "  IntelliFold PyTorch/MPS patch already applied"
else
  fail "IntelliFold source does not match the validated PyTorch/MPS patch base."
fi
INTELLIFOLD_FINAL_VENV="${INTELLIFOLD_VENV}"
begin_versioned_venv intellifold "${INTELLIFOLD_REV}" "${INTELLIFOLD_FINAL_VENV}" "${INTELLIFOLD_PYTHON_BIN}"
INTELLIFOLD_VENV="${TRANSACTION_VENV}"
if [[ "${TRANSACTION_REUSED}" -eq 0 ]]; then
  uv_install_locked "${INTELLIFOLD_VENV}/bin/python" "${INTELLIFOLD_LOCK}" \
    || fail "IntelliFold hash-locked dependency install failed."
  uv_install_editable "${INTELLIFOLD_VENV}/bin/python" "${INTELLIFOLD_REPO}" \
    || fail "IntelliFold install failed."
fi
# The unified, revision-checked patch above also carries the validated
# Apple-Silicon PyTorch changes. Keeping it atomic prevents a half-patched
# predictor from being reported as installed.
# Upstream defaults to ~/.intellifold and writes directly to final filenames.
# Keep every artifact under the managed root and route it through Studio's
# resumable, atomic checksum boundary instead. The immutable Hugging Face
# revision prevents a moving branch from changing bytes behind a known URL.
mkdir -p "${INTELLIFOLD_MODEL_DIR}"
INTELLIFOLD_HF_REV="8f5ec8ab39e89fabf1887e54fe5ce588aaaaf890"
download_intellifold() {
  local name="$1" checksum="$2" label="$3" start="$4" end="$5"
  download_verified_artifact "${INTELLIFOLD_VENV}/bin/python" \
    "${INTELLIFOLD_MODEL_DIR}/${name}" \
    "https://huggingface.co/intelligenAI/intellifold/resolve/${INTELLIFOLD_HF_REV}/${name}?download=true" \
    "${checksum}" "${label}" intellifold "${start}" "${end}"
}
download_intellifold "intellifold_v2_flash.pt" \
  "ac405f91c59a1b135dab0fbddd103d032bcb1ea1cb59f162348c0b90d4ab4fa5" \
  "IntelliFold v2 Flash checkpoint" 60 62
download_intellifold "ccd_v2.pkl" \
  "8766edb6a88e01461a123e8a4e2d5e33846821b808444737cd82e441998801f8" \
  "IntelliFold chemical-component dictionary" 62 63
download_intellifold "unique_protein_sequences.fasta" \
  "bcba48b77ee37b2eca0af50d05e71f7d68d36135b4884c47795d4d7ba47ac73f" \
  "IntelliFold protein sequence reference" 63 63
download_intellifold "unique_nucleic_acid_sequences.fasta" \
  "67c703969c2d3f28ff39eb0e20c28541bce45b44514f5a6cbccc8070d08e3ddf" \
  "IntelliFold nucleic-acid sequence reference" 63 63
download_intellifold "protein_id_groups.json" \
  "b5a46c434278f5ea1aedd8a84ac2c7664acc08817c244c7d13396d4459632eaa" \
  "IntelliFold protein ID groups" 63 63
download_intellifold "nucleic_acid_id_groups.json" \
  "0aa0da461f7a36eed6921b1b3f7ea59f50d806fb0c12f94073a3d3b052491d12" \
  "IntelliFold nucleic-acid ID groups" 63 63
if [[ "${WITH_INTELLIFOLD_FULL}" -eq 1 ]]; then
  download_intellifold "intellifold_v2.pt" \
    "8ee1c03344a94c8d3408f9579b3869f791701b7945e23255331d44fb7cc41aaa" \
    "IntelliFold full-v2 checkpoint" 63 64
fi
[[ -s "${INTELLIFOLD_MODEL_DIR}/intellifold_v2_flash.pt" \
   && -s "${INTELLIFOLD_MODEL_DIR}/ccd_v2.pkl" ]] \
  || fail "IntelliFold install finished without v2 Flash weights or CCD data."
"${INTELLIFOLD_VENV}/bin/python" \
  "${NANOHUNTER_ROOT}/scripts/intellifold_mps_compat.py" "${NANOHUNTER_ROOT}" \
  || fail "Could not install IntelliFold's Apple-MPS pair-lookup compatibility fix."
PYTORCH_ENABLE_MPS_FALLBACK=0 "${INTELLIFOLD_VENV}/bin/python" -c \
  'import torch, intellifold; assert torch.backends.mps.is_available()' >/dev/null \
  || fail "IntelliFold staged runtime failed its native-MPS import check."
commit_versioned_venv
INTELLIFOLD_VENV="${INTELLIFOLD_FINAL_VENV}"
  write_component_receipt intellifold "${INTELLIFOLD_REV}" "${INTELLIFOLD_VENV}/bin/python" \
    "native-mps-no-cpu-fallback" --lock "${INTELLIFOLD_LOCK}" \
    --source "${INTELLIFOLD_REPO}=${INTELLIFOLD_REV}" \
    --artifact "${INTELLIFOLD_MODEL_DIR}/intellifold_v2_flash.pt=ac405f91c59a1b135dab0fbddd103d032bcb1ea1cb59f162348c0b90d4ab4fa5" \
    --artifact "${INTELLIFOLD_MODEL_DIR}/ccd_v2.pkl=8766edb6a88e01461a123e8a4e2d5e33846821b808444737cd82e441998801f8" \
    --artifact "${INTELLIFOLD_MODEL_DIR}/unique_protein_sequences.fasta=bcba48b77ee37b2eca0af50d05e71f7d68d36135b4884c47795d4d7ba47ac73f" \
    --artifact "${INTELLIFOLD_MODEL_DIR}/unique_nucleic_acid_sequences.fasta=67c703969c2d3f28ff39eb0e20c28541bce45b44514f5a6cbccc8070d08e3ddf" \
    --artifact "${INTELLIFOLD_MODEL_DIR}/protein_id_groups.json=b5a46c434278f5ea1aedd8a84ac2c7664acc08817c244c7d13396d4459632eaa" \
    --artifact "${INTELLIFOLD_MODEL_DIR}/nucleic_acid_id_groups.json=0aa0da461f7a36eed6921b1b3f7ea59f50d806fb0c12f94073a3d3b052491d12"
state intellifold ok "IntelliFold v2 Flash (PyTorch/MPS)"
if [[ "${WITH_INTELLIFOLD_FULL}" -eq 1 ]]; then
  [[ -s "${INTELLIFOLD_MODEL_DIR}/intellifold_v2.pt" ]] \
    || fail "IntelliFold full-v2 checkpoint was requested but is absent."
  write_component_receipt intellifold_full "${INTELLIFOLD_REV}" "${INTELLIFOLD_VENV}/bin/python" \
    "native-mps-no-cpu-fallback" \
    --artifact "${INTELLIFOLD_MODEL_DIR}/intellifold_v2.pt=8ee1c03344a94c8d3408f9579b3869f791701b7945e23255331d44fb7cc41aaa"
  state intellifold_full ok "optional full-v2 checkpoint"
else
  state intellifold_full skipped "not requested"
fi
else
state intellifold skipped "not requested"
state intellifold_full skipped "not requested"
fi

# ---- Protenix Constraint v0.5 (isolated native-MPS profile) ----
# This is intentionally not installed into the v2/Mini runtime. The official
# constraint checkpoint has no trained ESM projection and must be strict-loaded
# with ESM disabled.
if [[ "${WITH_PROTENIX_CONSTRAINT}" -eq 1 ]]; then
  step protenix_constraint 61 "Installing Protenix Constraint v0.5 for the Apple GPU"
  ensure_pinned_repo "Protenix Constraint" "https://github.com/bytedance/Protenix.git" \
    "${PROTENIX_REV}" "${PROTENIX_CONSTRAINT_REPO}"
  [[ -f "${PROTENIX_CONSTRAINT_PATCH}" ]] || fail "Bundled Protenix Constraint MPS patch is missing."
  if git -C "${PROTENIX_CONSTRAINT_REPO}" apply --check "${PROTENIX_CONSTRAINT_PATCH}" >/dev/null 2>&1; then
    git -C "${PROTENIX_CONSTRAINT_REPO}" apply "${PROTENIX_CONSTRAINT_PATCH}" \
      || fail "Could not apply the validated Protenix Constraint MPS patch."
  elif git -C "${PROTENIX_CONSTRAINT_REPO}" apply --reverse --check "${PROTENIX_CONSTRAINT_PATCH}" >/dev/null 2>&1; then
    echo "  Protenix Constraint MPS patch already applied"
  else
    fail "Protenix Constraint source does not match the validated patch base."
  fi
  [[ -f "${PROTENIX_CONSTRAINT_ZERO_SUBSTRUCTURE_PATCH}" ]] \
    || fail "Bundled Protenix Constraint zero-substructure patch is missing."
  if git -C "${PROTENIX_CONSTRAINT_REPO}" apply --check "${PROTENIX_CONSTRAINT_ZERO_SUBSTRUCTURE_PATCH}" >/dev/null 2>&1; then
    git -C "${PROTENIX_CONSTRAINT_REPO}" apply "${PROTENIX_CONSTRAINT_ZERO_SUBSTRUCTURE_PATCH}" \
      || fail "Could not apply the validated Protenix Constraint zero-substructure patch."
  elif git -C "${PROTENIX_CONSTRAINT_REPO}" apply --reverse --check "${PROTENIX_CONSTRAINT_ZERO_SUBSTRUCTURE_PATCH}" >/dev/null 2>&1; then
    echo "  Protenix Constraint zero-substructure patch already applied"
  else
    fail "Protenix Constraint substructure source does not match the validated patch base."
  fi
  [[ -f "${PROTENIX_CONSTRAINT_LOCK}" ]] || fail "Constraint dependency lock is missing."
  [[ -f "${VERIFIED_DOWNLOADER}" ]] || fail "Bundled verified downloader is missing."
  PROTENIX_CONSTRAINT_FINAL_VENV="${PROTENIX_CONSTRAINT_VENV}"
  begin_versioned_venv protenix_constraint "${PROTENIX_REV}" \
    "${PROTENIX_CONSTRAINT_FINAL_VENV}" "${INTELLIFOLD_PYTHON_BIN}"
  PROTENIX_CONSTRAINT_VENV="${TRANSACTION_VENV}"
  if [[ "${TRANSACTION_REUSED}" -eq 0 ]]; then
    uv_install_locked "${PROTENIX_CONSTRAINT_VENV}/bin/python" \
      "${PROTENIX_CONSTRAINT_LOCK}" \
      || fail "Protenix Constraint locked dependency install failed."
    uv_install_editable "${PROTENIX_CONSTRAINT_VENV}/bin/python" \
      "${PROTENIX_CONSTRAINT_REPO}" \
      || fail "Protenix Constraint source install failed."
  fi
  if "${PROTENIX_CONSTRAINT_VENV}/bin/python" -c 'import importlib.metadata; importlib.metadata.version("fair-esm")' >/dev/null 2>&1; then
    fail "Constraint-only profile unexpectedly contains fair-esm; refusing an ambiguous runtime."
  fi

  seed_shared_protenix_common "${PROTENIX_CONSTRAINT_MODEL_DIR}"
  mkdir -p "${PROTENIX_CONSTRAINT_MODEL_DIR}/checkpoint" "${PROTENIX_COMMON_DIR}"
  download_protenix_constraint() {
    local relative="$1" url="$2" checksum="$3" label="$4" start="$5" end="$6"
    local output="${PROTENIX_CONSTRAINT_MODEL_DIR}/${relative}"
    [[ "${relative}" == common/* ]] \
      && output="${PROTENIX_COMMON_DIR}/${relative#common/}"
    "${PROTENIX_CONSTRAINT_VENV}/bin/python" "${VERIFIED_DOWNLOADER}" \
      --url "${url}" --sha256 "${checksum}" \
      --output "${output}" --label "${label}" \
      --progress-key protenix_constraint --progress-start "${start}" --progress-end "${end}" \
      || fail "Could not download or verify ${label}. The partial file was retained for resume."
  }
  download_protenix_constraint "checkpoint/protenix_base_constraint_v0.5.0.pt" \
    "https://protenix.tos-cn-beijing.volces.com/checkpoint/protenix_base_constraint_v0.5.0.pt" \
    "5358025b20b2212853ad75579be04387859557915f398a1d60f6a1a9a0c8c887" \
    "Protenix Constraint v0.5 checkpoint" 61 63
  [[ "$(stat -f%z "${PROTENIX_CONSTRAINT_MODEL_DIR}/checkpoint/protenix_base_constraint_v0.5.0.pt")" == "1475206741" ]] \
    || fail "Protenix Constraint checkpoint size does not match the validated release."
  download_protenix_constraint "common/components.cif" \
    "https://protenix.tos-cn-beijing.volces.com/common/components.cif" \
    "bb31ae5cf6c8bc669924313077cb4231ee5ffefd3a20118cd14f3ec89f8bb6a5" \
    "Protenix Constraint chemical components" 63 63
  download_protenix_constraint "common/components.cif.rdkit_mol.pkl" \
    "https://protenix.tos-cn-beijing.volces.com/common/components.cif.rdkit_mol.pkl" \
    "d1cfb71f5993a3ebea7c47877022d7f597bbfbaf86e28a4770e957da6c50cd35" \
    "Protenix Constraint RDKit cache" 63 64
  download_protenix_constraint "common/obsolete_release_date.csv" \
    "https://protenix.tos-cn-beijing.volces.com/common/obsolete_release_date.csv" \
    "a4f3f63ac5d7eebd78b07995cc669b9eccd6f5d8813c9492c9df02868893cf33" \
    "Protenix Constraint obsolete-entry table" 64 64
  download_protenix_constraint "common/clusters-by-entity-40.txt" \
    "https://protenix.tos-cn-beijing.volces.com/common/clusters-by-entity-40.txt" \
    "1ab4af905e75b382eda8dec59917dc3608bee0729e36b9e71baf860bbe86850c" \
    "Protenix Constraint sequence clusters" 64 64
  activate_shared_protenix_common "${PROTENIX_CONSTRAINT_MODEL_DIR}"

  PROTENIX_ROOT_DIR="${PROTENIX_CONSTRAINT_MODEL_DIR}" \
    "${PROTENIX_CONSTRAINT_VENV}/bin/python" - "${PROTENIX_CONSTRAINT_MODEL_DIR}/install_receipt.json" \
      "${PROTENIX_CONSTRAINT_REPO}" "${PROTENIX_CONSTRAINT_PATCH}" \
      "${PROTENIX_CONSTRAINT_ZERO_SUBSTRUCTURE_PATCH}" "${PROTENIX_CONSTRAINT_LOCK}" <<'PY' \
    || fail "Protenix Constraint runtime audit failed."
import hashlib, importlib.metadata, json, os, pathlib, subprocess, sys, torch
receipt_path, source, patch, zero_substructure_patch, lock = map(pathlib.Path, sys.argv[1:])
if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1" or not torch.backends.mps.is_available():
    raise SystemExit("native MPS is required and CPU fallback is forbidden")
try:
    importlib.metadata.version("fair-esm")
except importlib.metadata.PackageNotFoundError:
    pass
else:
    raise SystemExit("fair-esm is forbidden in the constraint profile")
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
payload = {"product": "Protenix Constraint v0.5 — Experimental",
 "model": "protenix_base_constraint_v0.5.0",
 "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
 "patch_sha256": digest(patch),
 "zero_substructure_patch_sha256": digest(zero_substructure_patch),
 "substructure_source_sha256": digest(source / "protenix/model/modules/embedders.py"),
 "requirements_sha256": digest(lock),
 "checkpoint_sha256": "5358025b20b2212853ad75579be04387859557915f398a1d60f6a1a9a0c8c887",
 "python": sys.version.split()[0], "torch": torch.__version__,
 "device_policy": "native-mps-fp32-no-cpu-fallback", "esm": "disabled-and-not-installed",
 "zero_substructure": "checkpoint-equivalent-single-token-broadcast"}
receipt_path.write_text(json.dumps(payload, indent=2) + "\n")
PY
  commit_versioned_venv
  PROTENIX_CONSTRAINT_VENV="${PROTENIX_CONSTRAINT_FINAL_VENV}"
  write_component_receipt protenix_constraint "${PROTENIX_REV}" \
    "${PROTENIX_CONSTRAINT_VENV}/bin/python" "native-mps-fp32-no-cpu-fallback" \
    --lock "${PROTENIX_CONSTRAINT_LOCK}" \
    --source "${PROTENIX_CONSTRAINT_REPO}=${PROTENIX_REV}" \
    --artifact "${PROTENIX_CONSTRAINT_MODEL_DIR}/checkpoint/protenix_base_constraint_v0.5.0.pt=5358025b20b2212853ad75579be04387859557915f398a1d60f6a1a9a0c8c887"
  state protenix_constraint ok "Protenix Constraint v0.5 (native MPS, strict ESM-free profile)"
else
  state protenix_constraint skipped "not requested"
fi

# ---- Protenix runtime + selected checkpoints (native Apple MPS) ----
if [[ "${WITH_PROTENIX_RUNTIME}" -eq 1 ]]; then
  step protenix 64 "Installing the shared Protenix runtime for the Apple GPU"
  ensure_pinned_repo "Protenix" "https://github.com/bytedance/Protenix.git" \
    "${PROTENIX_REV}" "${PROTENIX_REPO}"
  [[ -f "${PROTENIX_STUDIO_PATCH}" ]] \
    || fail "Bundled Protenix MPS patch is missing: ${PROTENIX_STUDIO_PATCH}"
  if git -C "${PROTENIX_REPO}" apply --check "${PROTENIX_STUDIO_PATCH}" >/dev/null 2>&1; then
    git -C "${PROTENIX_REPO}" apply "${PROTENIX_STUDIO_PATCH}" \
      || fail "Could not apply the validated Protenix MPS patch."
  elif git -C "${PROTENIX_REPO}" apply --reverse --check "${PROTENIX_STUDIO_PATCH}" >/dev/null 2>&1; then
    echo "  Protenix MPS patch already applied"
  else
    fail "Protenix source does not match the validated MPS patch base."
  fi

  [[ -f "${PROTENIX_LOCK}" ]] || fail "Bundled Protenix dependency lock is missing."
  [[ -f "${VERIFIED_DOWNLOADER}" ]] || fail "Bundled verified downloader is missing."
  PROTENIX_FINAL_VENV="${PROTENIX_VENV}"
  begin_versioned_venv protenix "${PROTENIX_REV}" "${PROTENIX_FINAL_VENV}" "${PYTHON_BIN}"
  PROTENIX_VENV="${TRANSACTION_VENV}"
  if [[ "${TRANSACTION_REUSED}" -eq 0 ]]; then
    uv_install_locked "${PROTENIX_VENV}/bin/python" "${PROTENIX_LOCK}" \
      || fail "Protenix locked dependency install failed."
    uv_install_editable "${PROTENIX_VENV}/bin/python" "${PROTENIX_REPO}" \
      || fail "Protenix source install failed."
  fi

  # Checkpoints and chemical data live in the managed runtime, never in Git.
  # Every transfer resumes its .part file after a timed read and only becomes
  # visible under the final name after its pinned SHA-256 matches.
  seed_shared_protenix_common "${PROTENIX_MODEL_DIR}"
  seed_shared_protenix_common "${PROTENIX_CONSTRAINT_MODEL_DIR}"
  mkdir -p "${PROTENIX_MODEL_DIR}/checkpoint" "${PROTENIX_COMMON_DIR}"
  PROTENIX_HF_REV="653edab28103133512575365130916e3fd23ecc3"
  download_protenix() {
    local relative="$1" url="$2" checksum="$3" label="$4" start="$5" end="$6"
    local output="${PROTENIX_MODEL_DIR}/${relative}"
    [[ "${relative}" == common/* ]] \
      && output="${PROTENIX_COMMON_DIR}/${relative#common/}"
    "${PROTENIX_VENV}/bin/python" "${VERIFIED_DOWNLOADER}" \
      --url "${url}" --sha256 "${checksum}" \
      --output "${output}" --label "${label}" \
      --progress-key protenix --progress-start "${start}" --progress-end "${end}" \
      || fail "Could not download or verify ${label}. The partial file was retained for resume."
  }
  if [[ "${WITH_PROTENIX_V2}" -eq 1 ]]; then
    download_protenix "checkpoint/protenix-v2.pt" \
      "https://huggingface.co/TMF001/protenix-v2-weights/resolve/${PROTENIX_HF_REV}/protenix-v2.pt?download=true" \
      "8f931f9774a396b67033d0e58628e1834f4a1448165e04254b40a780b0c0d599" \
      "Protenix v2 checkpoint" 64 70
    state protenix_v2 ok "Protenix v2 checkpoint"
  else
    state protenix_v2 skipped "not requested"
  fi
  if [[ "${WITH_PROTENIX_MINI}" -eq 1 ]]; then
    download_protenix "checkpoint/protenix_mini_default_v0.5.0.pt" \
      "https://protenix.tos-cn-beijing.volces.com/checkpoint/protenix_mini_default_v0.5.0.pt" \
      "3803340c5d9958c038e799ddd2b53b532db21855f261592ad455a5f003791f81" \
      "Protenix Mini checkpoint" 70 73
    state protenix_mini ok "Protenix Mini checkpoint"
  else
    state protenix_mini skipped "not requested"
  fi
  download_protenix "common/components.cif" \
    "https://protenix.tos-cn-beijing.volces.com/common/components.cif" \
    "bb31ae5cf6c8bc669924313077cb4231ee5ffefd3a20118cd14f3ec89f8bb6a5" \
    "Protenix chemical components" 73 77
  download_protenix "common/components.cif.rdkit_mol.pkl" \
    "https://protenix.tos-cn-beijing.volces.com/common/components.cif.rdkit_mol.pkl" \
    "d1cfb71f5993a3ebea7c47877022d7f597bbfbaf86e28a4770e957da6c50cd35" \
    "Protenix RDKit component cache" 77 79
  download_protenix "common/obsolete_release_date.csv" \
    "https://protenix.tos-cn-beijing.volces.com/common/obsolete_release_date.csv" \
    "a4f3f63ac5d7eebd78b07995cc669b9eccd6f5d8813c9492c9df02868893cf33" \
    "Protenix obsolete-entry table" 79 80
  download_protenix "common/clusters-by-entity-40.txt" \
    "https://protenix.tos-cn-beijing.volces.com/common/clusters-by-entity-40.txt" \
    "1ab4af905e75b382eda8dec59917dc3608bee0729e36b9e71baf860bbe86850c" \
    "Protenix sequence clusters" 80 81
  activate_shared_protenix_common "${PROTENIX_MODEL_DIR}"

  PROTENIX_ROOT_DIR="${PROTENIX_MODEL_DIR}" "${PROTENIX_VENV}/bin/python" - <<'PY' \
    || fail "Protenix cannot use the Apple GPU on this Mac. CPU fallback is intentionally disabled."
import torch
if not torch.backends.mps.is_available():
    raise SystemExit("Metal Performance Shaders is unavailable")
import protenix
print(f"  Protenix ready on {torch.device('mps')}")
PY
  commit_versioned_venv
  PROTENIX_VENV="${PROTENIX_FINAL_VENV}"
  write_component_receipt protenix "${PROTENIX_REV}" "${PROTENIX_VENV}/bin/python" \
    "native-mps-fp32-no-cpu-fallback" --lock "${PROTENIX_LOCK}" \
    --source "${PROTENIX_REPO}=${PROTENIX_REV}" \
    --artifact "${PROTENIX_COMMON_DIR}/components.cif=bb31ae5cf6c8bc669924313077cb4231ee5ffefd3a20118cd14f3ec89f8bb6a5" \
    --artifact "${PROTENIX_COMMON_DIR}/components.cif.rdkit_mol.pkl=d1cfb71f5993a3ebea7c47877022d7f597bbfbaf86e28a4770e957da6c50cd35" \
    --artifact "${PROTENIX_COMMON_DIR}/obsolete_release_date.csv=a4f3f63ac5d7eebd78b07995cc669b9eccd6f5d8813c9492c9df02868893cf33" \
    --artifact "${PROTENIX_COMMON_DIR}/clusters-by-entity-40.txt=1ab4af905e75b382eda8dec59917dc3608bee0729e36b9e71baf860bbe86850c"
  if [[ "${WITH_PROTENIX_V2}" -eq 1 ]]; then
    write_component_receipt protenix_v2 "${PROTENIX_HF_REV}" "${PROTENIX_VENV}/bin/python" \
      "native-mps-fp32-no-cpu-fallback" \
      --artifact "${PROTENIX_MODEL_DIR}/checkpoint/protenix-v2.pt=8f931f9774a396b67033d0e58628e1834f4a1448165e04254b40a780b0c0d599"
  fi
  if [[ "${WITH_PROTENIX_MINI}" -eq 1 ]]; then
    write_component_receipt protenix_mini "0.5.0" "${PROTENIX_VENV}/bin/python" \
      "native-mps-fp32-no-cpu-fallback" \
      --artifact "${PROTENIX_MODEL_DIR}/checkpoint/protenix_mini_default_v0.5.0.pt=3803340c5d9958c038e799ddd2b53b532db21855f261592ad455a5f003791f81"
  fi
  state protenix ok "shared native-MPS runtime and chemical data"
else
  state protenix skipped "not requested"
  state protenix_v2 skipped "not requested"
  state protenix_mini skipped "not requested"
fi

# ---- LASErMPNN (ligand-aware inverse folding) ----
if [[ "${WITH_LASERMPNN}" -eq 1 ]]; then
  step lasermpnn 82 "Installing LASErMPNN (ligand-aware sequence design)"
  LASERMPNN_REPO="${SRC_DIR}/LASErMPNN"
  LASERMPNN_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_lasermpnn"
  ensure_pinned_repo "LASErMPNN" "https://github.com/polizzilab/LASErMPNN.git" \
    "${LASERMPNN_REV}" "${LASERMPNN_REPO}"
  LASERMPNN_FINAL_VENV="${LASERMPNN_VENV}"
  begin_versioned_venv lasermpnn "${LASERMPNN_REV}" "${LASERMPNN_FINAL_VENV}" "${PYTHON_BIN}"
  LASERMPNN_VENV="${TRANSACTION_VENV}"
  if [[ "${TRANSACTION_REUSED}" -eq 0 ]]; then
    [[ -f "${LASERMPNN_LOCK}" && -f "${LASERMPNN_BOOTSTRAP_LOCK}" ]] \
      || fail "LASErMPNN hash locks are missing."
  # torch-scatter/torch-cluster have no MPS kernels, so this runs on CPU. It is
  # seconds per design, so CPU is not the bottleneck.
  # This is the validated Apple-Silicon environment from NanoHunter. PyTorch
  # 2.2.x uses the NumPy 1.x ABI; the PyG extensions must be compiled against
  # that exact installed torch rather than in pip's isolated build env.
  uv_install_locked "${LASERMPNN_VENV}/bin/python" "${LASERMPNN_BOOTSTRAP_LOCK}" \
    || fail "LASErMPNN hash-locked build bootstrap failed."
  # The macOS 26 libc++ headers mark std::is_arithmetic as unspecialisable;
  # PyTorch 2.2.1's strong_type.h predates that annotation. Clang exposes this
  # exact compatibility diagnostic as -Winvalid-specialization. Suppressing it
  # restores the previously validated build without hiding other C++ errors.
  MACOSX_DEPLOYMENT_TARGET=11.0 CXXFLAGS="-Wno-invalid-specialization" \
    uv_install_locked "${LASERMPNN_VENV}/bin/python" "${LASERMPNN_LOCK}" \
      --no-build-isolation \
    || fail "LASErMPNN hash-locked dependency/extension build failed."
  fi
  (cd "${SRC_DIR}" && "${LASERMPNN_VENV}/bin/python" -c \
    "import LASErMPNN.run_batch_inference; from torch_cluster import knn_graph; from torch_scatter import scatter") \
    >/dev/null 2>&1 || fail "LASErMPNN staged import check failed."
  commit_versioned_venv
  LASERMPNN_VENV="${LASERMPNN_FINAL_VENV}"
  write_component_receipt lasermpnn "${LASERMPNN_REV}" "${LASERMPNN_VENV}/bin/python" \
    "cpu-required-upstream-kernels" --lock "${LASERMPNN_LOCK}" \
    --source "${LASERMPNN_REPO}=${LASERMPNN_REV}" \
    --artifact "${LASERMPNN_REPO}/model_weights/laser_weights_0p1A_nothing_heldout.pt=304fe02a4807c310bdd9d68c988ae87619da3cf2025d5c223fb31030aa411173"
  state lasermpnn ok "LASErMPNN (CPU)"
else
  state lasermpnn skipped "not requested"
fi

# ---- OpenFold-3-MLX (optional predictor) ----
if [[ "${WITH_OPENFOLD3}" -eq 1 ]]; then
  step openfold3 87 "Installing OpenFold-3 (MLX kernels) — downloading ~2 GB checkpoint"
  ensure_pinned_repo "openfold-3-mlx" "https://github.com/latent-spacecraft/openfold-3-mlx.git" \
    "${OPENFOLD_REV}" "${OPENFOLD_REPO}"
  OPENFOLD_FINAL_VENV="${OPENFOLD_VENV}"
  begin_versioned_venv openfold3 "${OPENFOLD_REV}" "${OPENFOLD_FINAL_VENV}" "${PYTHON_BIN}"
  OPENFOLD_VENV="${TRANSACTION_VENV}"
  if [[ "${TRANSACTION_REUSED}" -eq 0 ]]; then
    uv_install_locked "${OPENFOLD_VENV}/bin/python" "${OPENFOLD_LOCK}" \
      || fail "OpenFold hash-locked dependency install failed."
    uv_install_editable "${OPENFOLD_VENV}/bin/python" "${OPENFOLD_REPO}" \
      || fail "openfold-3-mlx install failed."
  fi
  mkdir -p "${OPENFOLD_MODEL_DIR}"
  download_verified_artifact "${OPENFOLD_VENV}/bin/python" \
    "${OPENFOLD_CHECKPOINT_PATH}" \
    "https://openfold.s3.amazonaws.com/openfold3_params/of3_ft3_v1.pt" \
    "aedd8f3eb814e3926c8974ef34c9499df224443f173b7e396c97684da6e3eeb6" \
    "OpenFold-3 checkpoint" openfold3 87 95
  MLX_METAL_PREWARM=1 "${OPENFOLD_VENV}/bin/python" -c \
    'import mlx.core as mx, torch; assert mx.metal.is_available()' >/dev/null \
    || fail "OpenFold staged runtime failed its MLX health check."
  commit_versioned_venv
  OPENFOLD_VENV="${OPENFOLD_FINAL_VENV}"
  write_component_receipt openfold3 "${OPENFOLD_REV}" "${OPENFOLD_VENV}/bin/python" \
    "mlx-and-mps-no-cpu-option" --lock "${OPENFOLD_LOCK}" \
    --source "${OPENFOLD_REPO}=${OPENFOLD_REV}" \
    --artifact "${OPENFOLD_CHECKPOINT_PATH}=aedd8f3eb814e3926c8974ef34c9499df224443f173b7e396c97684da6e3eeb6"
  state openfold3 ok "OpenFold-3-MLX"
else
  state openfold3 skipped "not requested"
fi

# ---- RFdiffusion3 (optional backbone generator) ----
if [[ "${WITH_RFD3}" -eq 1 ]]; then
  step rfd3 96 "Installing RFdiffusion3 (MLX)"
  # The MLX port is the upstream this workflow extends. None of the campaign
  # orchestrators, ligand preparation or predictor adapters are in it -- those
  # arrive from the overlay below, which the app stages out of its own bundle.
  ensure_pinned_repo "RFdiffusion3 MLX" "https://github.com/javierbq/rfd3-mlx.git" \
    "${RFD3_REV}" "${RFD3_ROOT}"

  # Apply the overlay before installing: install_rfd3.sh calls scripts that only
  # exist because of it, so a clean clone fails without this.
  if [[ -d "${STUDIO_RFD3_OVERLAY}" && -d "${RFD3_ROOT}" ]]; then
    mkdir -p "${RFD3_ROOT}/scripts"
    cp -f "${STUDIO_RFD3_OVERLAY}"/scripts/*.py "${RFD3_ROOT}/scripts/" 2>/dev/null || true
    cp -f "${VERIFIED_DOWNLOADER}" "${RFD3_ROOT}/scripts/download_verified.py" \
      || fail "Could not stage the verified downloader for RFdiffusion3."
    for extra in milestone0_oracle.py export_weights.py rfd3_weight_set.py install_rfd3.sh \
                 requirements-rfd3.txt rfd3_env.sh; do
      [[ -f "${STUDIO_RFD3_OVERLAY}/${extra}" ]] && cp -f "${STUDIO_RFD3_OVERLAY}/${extra}" "${RFD3_ROOT}/"
    done
    if [[ -d "${STUDIO_RFD3_OVERLAY}/mlx_port" ]]; then
      mkdir -p "${RFD3_ROOT}/mlx_port"
      cp -f "${STUDIO_RFD3_OVERLAY}"/mlx_port/*.py "${RFD3_ROOT}/mlx_port/" \
        || fail "Could not stage the RFdiffusion3 MLX compatibility layer."
    fi
    [[ -d "${STUDIO_RFD3_OVERLAY}/assets" ]] && cp -R "${STUDIO_RFD3_OVERLAY}/assets/." "${RFD3_ROOT}/assets/" 2>/dev/null
    chmod 755 "${RFD3_ROOT}"/scripts/*.py "${RFD3_ROOT}"/*.sh 2>/dev/null || true
    [[ -f "${STUDIO_RFD3_OVERLAY}/OVERLAY_VERSION" ]] && \
      cp -f "${STUDIO_RFD3_OVERLAY}/OVERLAY_VERSION" "${RFD3_ROOT}/.studio_overlay_version"
    echo "  applied the RFdiffusion3 script overlay"
  fi

  if [[ -x "${RFD3_ROOT}/install_rfd3.sh" ]]; then
    mkdir -p "${NANOHUNTER_ROOT}/logs"
    RFD3_INSTALL_LOG="${NANOHUNTER_ROOT}/logs/rfd3-install.log"
    IPROTEINSTUDIO_DOWNLOADER="${VERIFIED_DOWNLOADER}" \
      IPROTEINSTUDIO_UV_BIN="${UV_BIN}" \
      IPROTEINSTUDIO_PYTHON_BIN="${INTELLIFOLD_PYTHON_BIN}" \
      bash "${RFD3_ROOT}/install_rfd3.sh" --download-weights 2>&1 \
      | tee "${RFD3_INSTALL_LOG}" \
      || fail "RFdiffusion3 install failed — see ${RFD3_INSTALL_LOG}"
    write_component_receipt rfd3 "${RFD3_REV}" "${RFD3_ROOT}/.venv/bin/python" \
      "native-mlx-no-cpu-option" \
      --source "${RFD3_ROOT}=${RFD3_REV}" \
      --artifact "${RFD3_CHECKPOINT_PATH}=9b3f85923e0d51e9453e15cdd2f8c666e7ce096a60577f57d11bbc54ae6d67c1" \
      --artifact "${RFD3_WEIGHTS_PATH}=${RFD3_WEIGHTS_SHA}"
    state rfd3 ok "RFdiffusion3 MLX"
  else
    fail "No RFdiffusion3 checkout at ${RFD3_ROOT}."
  fi
else
  state rfd3 skipped "not requested"
fi

step done 100 "Setup complete"
echo "NHDONE|ok"
