#!/usr/bin/env bash
# NanoHunter Studio pipeline setup.
#
# Installs the design backends into the app's managed directory. Core backends
# are always installed; the heavier predictors are opt-in because they cost
# gigabytes and, in AlphaFold 3's case, need weights the user must obtain
# themselves under Google's terms.
#
#   Core     Boltz-2 · LigandMPNN family (+AbMPNN) · AntiFold · IntelliFold
#   Optional --with-openfold3        OpenFold-3-MLX      (~2.1 GB checkpoint)
#            --with-alphafold3       AlphaFold 3 3.0.4   (weights NOT downloaded)
#            --with-intellifold-jax  IntelliFold JAX/MPS (1.24x, needs AF3 env)
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

NANOHUNTER_ROOT="${NANOHUNTER_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
VENV_PREFIX="${NANOHUNTER_VENV_PREFIX:-NanoHunter}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
ANTIFOLD_PYTHON_BIN="${ANTIFOLD_PYTHON_BIN:-python3.10}"
INTELLIFOLD_PYTHON_BIN="${INTELLIFOLD_PYTHON_BIN:-python3.12}"
LOCAL_BIN="${HOME}/.local/bin"
UV_BIN="${LOCAL_BIN}/uv"

WITH_OPENFOLD3=0
WITH_ALPHAFOLD3=0
WITH_INTELLIFOLD_JAX=0
WITH_RFD3=0
WITH_LASERMPNN=0
MATERIALISE=0
REPAIR_VENVS=0
LINK_EXISTING=""
LINK_RFD3=""
DETECT_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-openfold3)       WITH_OPENFOLD3=1; shift ;;
    --with-alphafold3)      WITH_ALPHAFOLD3=1; shift ;;
    --with-intellifold-jax) WITH_INTELLIFOLD_JAX=1; WITH_ALPHAFOLD3=1; shift ;;
    --with-rfd3)            WITH_RFD3=1; shift ;;
    --link-existing)        LINK_EXISTING="$2"; shift 2 ;;
    --materialise|--materialize) MATERIALISE=1; shift ;;
    --all)                  WITH_OPENFOLD3=1; WITH_ALPHAFOLD3=1; WITH_INTELLIFOLD_JAX=1
                            WITH_LASERMPNN=1; WITH_RFD3=1; shift ;;
    --with-lasermpnn)       WITH_LASERMPNN=1; shift ;;
    --link-rfd3)            LINK_RFD3="$2"; shift 2 ;;
    --detect)               DETECT_ONLY=1; shift ;;
    --repair-venvs)         REPAIR_VENVS=1; shift ;;
    *) echo "NHFAIL|Unknown option: $1"; exit 2 ;;
  esac
done

SRC_DIR="${NANOHUNTER_ROOT}/src"
BOLTZ_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_boltz"
LIGAND_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_ligandmpnn"
ANTIFOLD_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_antifold"
INTELLIFOLD_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_intellifold"
OPENFOLD_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_openfold3_mlx"
ALPHAFOLD3_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_alphafold3"
LIGANDMPNN_REPO="${SRC_DIR}/LigandMPNN"
ANTIFOLD_REPO="${SRC_DIR}/AntiFold"
INTELLIFOLD_REPO="${SRC_DIR}/IntelliFold"
OPENFOLD_REPO="${SRC_DIR}/openfold-3-mlx"
ALPHAFOLD3_REPO="${SRC_DIR}/alphafold3"
ALPHAFOLD3_MODEL_DIR="${NANOHUNTER_ROOT}/models/alphafold3"
INTELLIFOLD_JAX_MODEL_DIR="${NANOHUNTER_ROOT}/models/intellifold_jax_flash"
RFD3_ROOT="${NANOHUNTER_ROOT}/rfd3"
# Staged out of the app bundle next to this script; absent when the script is
# run standalone, in which case the overlay step is simply skipped.
STUDIO_RFD3_OVERLAY="${NANOHUNTER_ROOT}/rfd3_overlay"

step()  { echo "NHSTEP|$1|$2|$3"; }
state() { echo "NHSTATE|$1|$2|$3"; }
fail()  { echo "NHFAIL|$1"; exit 1; }

# ---------------------------------------------------------------- detection --

detect() {
  [[ -x "${BOLTZ_VENV}/bin/python" ]]       && state boltz ok "$(basename "${BOLTZ_VENV}")"       || state boltz missing ""
  [[ -x "${LIGAND_VENV}/bin/python" ]]      && state mpnn ok "LigandMPNN family"                  || state mpnn missing ""
  [[ -x "${ANTIFOLD_VENV}/bin/python" ]]    && state antifold ok "AntiFold"                       || state antifold missing ""
  [[ -x "${INTELLIFOLD_VENV}/bin/python" ]] && state intellifold ok "IntelliFold PyTorch/MPS"     || state intellifold missing ""
  [[ -x "${OPENFOLD_VENV}/bin/python" ]]    && state openfold3 ok "OpenFold-3-MLX"                || state openfold3 missing ""
  # LASErMPNN is ligand-aware inverse folding, used by both design tabs for
  # small-molecule targets. It has no MPS build, so it runs on CPU.
  if [[ -x "${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_lasermpnn/bin/python" \
     && -d "${NANOHUNTER_ROOT}/src/LASErMPNN" ]]; then
    state lasermpnn ok "LASErMPNN"
  else
    state lasermpnn missing ""
  fi
  if [[ -x "${ALPHAFOLD3_VENV}/bin/python" ]]; then
    if [[ -f "${ALPHAFOLD3_MODEL_DIR}/af3.bin" ]]; then
      state alphafold3 ok "AlphaFold 3 with weights"
    else
      state alphafold3 missing "environment installed, af3.bin weights absent"
    fi
  else
    state alphafold3 missing ""
  fi
  [[ -d "${INTELLIFOLD_JAX_MODEL_DIR}" ]] && state intellifold_jax ok "JAX/MPS v2-flash" || state intellifold_jax missing ""
  if [[ -x "${RFD3_ROOT}/.venv/bin/python" ]]; then
    [[ -f "${RFD3_ROOT}/weights/rfd3_core.safetensors" ]] \
      && state rfd3 ok "RFdiffusion3 MLX with exported weights" \
      || state rfd3 missing "environment installed, MLX weights absent"
  else
    state rfd3 missing ""
  fi
}

if [[ "${DETECT_ONLY}" -eq 1 ]]; then
  detect
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
    "venvs/${VENV_PREFIX}_openfold3_mlx" \
    "venvs/${VENV_PREFIX}_alphafold3" \
    "venvs/${VENV_PREFIX}_lasermpnn" \
    "src/LigandMPNN" "src/AntiFold" "src/IntelliFold" \
    "src/openfold-3-mlx" "src/alphafold3" "src/LASErMPNN" \
    "models/alphafold3" "models/intellifold_jax_flash"
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
    found="$(LC_ALL=C grep -o "/[^\"']*/venvs/${name}" "${script}" 2>/dev/null | head -n 1 || true)"
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
  local venv="${1%/}" old_root="$2" new_root="$3"
  [[ -n "${old_root}" && "${old_root}" != "${new_root}" ]] || return 0
  local site rewritten=0 file
  for site in "${venv}"/lib/python*/site-packages; do
    [[ -d "${site}" ]] || continue
    while IFS= read -r file; do
      [[ -n "${file}" ]] || continue
      LC_ALL=C sed -i '' "s|${old_root}|${new_root}|g" "${file}" 2>/dev/null && rewritten=$((rewritten+1))
    done < <(LC_ALL=C grep -rl "${old_root}" "${site}" \
               --include='*.pth' --include='*.egg-link' --include='__editable__*' 2>/dev/null)
  done
  [[ "${rewritten}" -eq 0 ]] || echo "  re-pointed ${rewritten} editable install(s) in $(basename "${venv}")"
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
  for venv in "${NANOHUNTER_ROOT}"/venvs/*/; do
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
  for probe in "venvs/${VENV_PREFIX}_openfold3_mlx" "venvs/${VENV_PREFIX}_alphafold3" "src/alphafold3"; do
    if [[ -L "${NANOHUNTER_ROOT}/${probe}" ]]; then
      MATERIALISE_SOURCE="$(readlink "${NANOHUNTER_ROOT}/${probe}")"
      MATERIALISE_SOURCE="${MATERIALISE_SOURCE%/${probe}}"
      break
    fi
  done
  for rel in \
    "venvs/${VENV_PREFIX}_boltz" "venvs/${VENV_PREFIX}_ligandmpnn" \
    "venvs/${VENV_PREFIX}_antifold" "venvs/${VENV_PREFIX}_intellifold" \
    "venvs/${VENV_PREFIX}_openfold3_mlx" "venvs/${VENV_PREFIX}_alphafold3" \
    "venvs/${VENV_PREFIX}_lasermpnn" \
    "src/LigandMPNN" "src/AntiFold" "src/IntelliFold" \
    "src/openfold-3-mlx" "src/alphafold3" "src/LASErMPNN" \
    "models/alphafold3" "models/intellifold_jax_flash" \
    "rfd3" "venvs" "src" "models"
  do
    materialise_component "${rel}" || failed=1
  done
  # A copied venv still points at where it came from: every console script in
  # bin/ carries a shebang with the *original* absolute path. Left alone the
  # copy would silently keep using the original environment, which defeats the
  # point of making this installation self-contained -- and would break the
  # moment the original was deleted.
  for venv in "${NANOHUNTER_ROOT}"/venvs/*/; do
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
  [[ -x "${UV_BIN}" ]] && return 0
  command -v uv >/dev/null 2>&1 && { UV_BIN="$(command -v uv)"; return 0; }
  mkdir -p "${LOCAL_BIN}"
  curl -LsSf https://astral.sh/uv/install.sh | sh || fail "Could not install uv (Python manager)."
}

ensure_python() {
  local want="$1" var="$2"
  local cur="${!var}"
  if command -v "${cur}" >/dev/null 2>&1; then printf -v "$var" '%s' "$(command -v "${cur}")"; return 0; fi
  ensure_uv
  "${UV_BIN}" python install "${want}" || fail "Could not install Python ${want}."
  export PATH="${LOCAL_BIN}:${PATH}"
  command -v "python${want}" >/dev/null 2>&1 || fail "Python ${want} still unavailable after install."
  printf -v "$var" '%s' "$(command -v "python${want}")"
}

# A shebang line cannot contain a space: the kernel splits on whitespace, so a
# console script installed under ".../Application Support/..." fails with
# "bad interpreter". Every venv pip creates here would be quietly broken.
case "${NANOHUNTER_ROOT}" in
  *" "*) fail "The install path contains a space (${NANOHUNTER_ROOT}). Python console scripts cannot run from such a path. Use a path without spaces, e.g. ~/.nanohunterstudio." ;;
esac

mkdir -p "${NANOHUNTER_ROOT}"/{venvs,src,examples,models,output}

step python 2 "Preparing Python environments"
command -v git >/dev/null 2>&1 || fail "git not found. Install Xcode Command Line Tools: xcode-select --install"
ensure_python 3.11 PYTHON_BIN
ensure_python 3.10 ANTIFOLD_PYTHON_BIN
ensure_python 3.12 INTELLIFOLD_PYTHON_BIN

# ---- Boltz (default design predictor) ----
step boltz 8 "Installing Boltz-2 design engine"
[[ -d "${BOLTZ_VENV}" ]] || "${PYTHON_BIN}" -m venv "${BOLTZ_VENV}" || fail "Boltz venv creation failed."
source "${BOLTZ_VENV}/bin/activate"
pip install --upgrade pip >/dev/null || fail "pip upgrade failed (Boltz)."
pip install torch >/dev/null || fail "torch install failed (Boltz)."
pip install boltz >/dev/null || fail "boltz install failed."
deactivate
state boltz ok "Boltz-2"

# ---- LigandMPNN family (+ AbMPNN weights) ----
step ligandmpnn 22 "Installing sequence designers (ProteinMPNN / SolubleMPNN / LigandMPNN / AbMPNN)"
[[ -d "${LIGAND_VENV}" ]] || "${PYTHON_BIN}" -m venv "${LIGAND_VENV}" || fail "LigandMPNN venv creation failed."
source "${LIGAND_VENV}/bin/activate"
pip install --upgrade pip >/dev/null || fail "pip upgrade failed (LigandMPNN)."
pip install torch==2.2.1 >/dev/null || fail "torch install failed (LigandMPNN)."
if [[ ! -d "${LIGANDMPNN_REPO}" ]]; then
  git clone --depth 1 https://github.com/dauparas/LigandMPNN.git "${LIGANDMPNN_REPO}" || fail "LigandMPNN clone failed."
fi
REQ_OUT="${LIGANDMPNN_REPO}/requirements.macos_nocuda.txt"
grep -Ev 'cuda|cublas|cudnn|nccl|nvidia|triton' "${LIGANDMPNN_REPO}/requirements.txt" > "${REQ_OUT}"
pip install -r "${REQ_OUT}" >/dev/null || fail "LigandMPNN requirements install failed."
MODEL_DIR="${LIGANDMPNN_REPO}/model_params"; mkdir -p "${MODEL_DIR}"
step weights 32 "Downloading designer weights"
python - "${MODEL_DIR}" <<'PY' || exit 1
import sys, urllib.request, pathlib
out = pathlib.Path(sys.argv[1])
urls = {
  "proteinmpnn_v_48_020.pt": "https://files.ipd.uw.edu/pub/ligandmpnn/proteinmpnn_v_48_020.pt",
  "solublempnn_v_48_020.pt": "https://files.ipd.uw.edu/pub/ligandmpnn/solublempnn_v_48_020.pt",
  "ligandmpnn_v_32_010_25.pt": "https://files.ipd.uw.edu/pub/ligandmpnn/ligandmpnn_v_32_010_25.pt",
  "abmpnn.pt": "https://zenodo.org/records/8164693/files/abmpnn.pt?download=1",
}
for name, url in urls.items():
    p = out / name
    if p.exists() and p.stat().st_size > 0:
        print(f"  have {name}"); continue
    print(f"  downloading {name}")
    urllib.request.urlretrieve(url, p)
    if p.stat().st_size == 0:
        print(f"NHFAIL|empty download {name}"); sys.exit(1)
PY
deactivate
state mpnn ok "ProteinMPNN / SolubleMPNN / LigandMPNN / AbMPNN"

# ---- AntiFold (antibody-aware designer, nanobody default) ----
step antifold 45 "Installing AntiFold (antibody-aware designer)"
[[ -d "${ANTIFOLD_REPO}" ]] || git clone --depth 1 https://github.com/oxpig/AntiFold.git "${ANTIFOLD_REPO}" || fail "AntiFold clone failed."
[[ -d "${ANTIFOLD_VENV}" ]] || "${ANTIFOLD_PYTHON_BIN}" -m venv "${ANTIFOLD_VENV}" || fail "AntiFold venv creation failed."
source "${ANTIFOLD_VENV}/bin/activate"
pip install --upgrade pip >/dev/null || fail "pip upgrade failed (AntiFold)."
pip install torch==2.2.0 >/dev/null || fail "torch install failed (AntiFold)."
pip install torch_geometric==2.4.0 biopython==1.83 biotite==0.38 "pygam==0.9.*" "numpy==1.26.*" "pandas==2.*" >/dev/null \
  || fail "AntiFold dependency install failed."
pip install -e "${ANTIFOLD_REPO}" --no-deps >/dev/null || fail "AntiFold install failed."
ANTIFOLD_MODEL_PATH="${ANTIFOLD_REPO}/models/model.pt"
python - "${ANTIFOLD_MODEL_PATH}" <<'PY' || exit 1
import pathlib, sys, urllib.request
t = pathlib.Path(sys.argv[1]); t.parent.mkdir(parents=True, exist_ok=True)
if t.exists() and t.stat().st_size > 0: print("  have antifold weights"); sys.exit(0)
print("  downloading antifold weights")
urllib.request.urlretrieve("https://opig.stats.ox.ac.uk/data/downloads/AntiFold/models/model.pt", t)
PY
deactivate
state antifold ok "AntiFold"

# ---- IntelliFold (default post predictor) ----
step intellifold 60 "Installing IntelliFold prediction engine"
[[ -d "${INTELLIFOLD_REPO}" ]] || git clone --depth 1 https://github.com/IntelliGen-AI/IntelliFold.git "${INTELLIFOLD_REPO}" || fail "IntelliFold clone failed."
[[ -d "${INTELLIFOLD_VENV}" ]] || "${INTELLIFOLD_PYTHON_BIN}" -m venv "${INTELLIFOLD_VENV}" || fail "IntelliFold venv creation failed."
source "${INTELLIFOLD_VENV}/bin/activate"
pip install --upgrade pip >/dev/null || fail "pip upgrade failed (IntelliFold)."
pip install torch==2.6.0 >/dev/null || fail "torch install failed (IntelliFold)."
pip install -e "${INTELLIFOLD_REPO}" --no-deps >/dev/null || fail "IntelliFold install failed."
pip install accelerate==1.1.1 biopython==1.85 click==8.1.8 einops==0.8.0 einx==0.3.0 ihm==2.5 \
  mashumaro==3.14 ml_collections==1.0.0 modelcif==1.2 networkx==3.4.2 numba==0.61.0 numpy==1.26.4 \
  pandas==2.2.3 pyyaml==6.0.2 rdkit==2026.3.3 requests==2.32.3 scipy==1.14.1 torchdiffeq==0.2.5 \
  tqdm==4.67.1 fsspec==2025.3.0 zstandard==0.23.0 ml_dtypes==0.5.3 >/dev/null \
  || fail "IntelliFold dependency install failed."
deactivate
# Idempotent Apple-Silicon patch: skip CUDA-only empty_cache()/pinned-memory
# paths when the device is not CUDA. Verified to leave structures and all
# confidence metrics byte-identical (NanoHunter docs/MPS_OPTIMIZATION.md).
if [[ -f "${NANOHUNTER_ROOT}/scripts/patch_intellifold_mps.py" ]]; then
  "${INTELLIFOLD_VENV}/bin/python" "${NANOHUNTER_ROOT}/scripts/patch_intellifold_mps.py" \
    --repo "${INTELLIFOLD_REPO}" >/dev/null 2>&1 \
    || echo "  note: IntelliFold MPS patch not applied (non-fatal)"
fi
state intellifold ok "IntelliFold v2-flash (PyTorch/MPS)"

# ---- LASErMPNN (ligand-aware inverse folding) ----
if [[ "${WITH_LASERMPNN}" -eq 1 ]]; then
  step lasermpnn 66 "Installing LASErMPNN (ligand-aware sequence design)"
  LASERMPNN_REPO="${SRC_DIR}/LASErMPNN"
  LASERMPNN_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_lasermpnn"
  [[ -d "${LASERMPNN_REPO}" ]] || git clone --depth 1 https://github.com/polizzilab/LASErMPNN.git "${LASERMPNN_REPO}" \
    || fail "LASErMPNN clone failed."
  [[ -d "${LASERMPNN_VENV}" ]] || "${PYTHON_BIN}" -m venv "${LASERMPNN_VENV}" || fail "LASErMPNN venv creation failed."
  source "${LASERMPNN_VENV}/bin/activate"
  pip install --upgrade pip >/dev/null || fail "pip upgrade failed (LASErMPNN)."
  # torch-scatter/torch-cluster have no MPS kernels, so this runs on CPU. It is
  # seconds per design, so CPU is not the bottleneck.
  pip install torch >/dev/null || fail "torch install failed (LASErMPNN)."
  pip install torch-scatter torch-cluster >/dev/null 2>&1 || \
    echo "  note: torch-scatter/torch-cluster build failed; LASErMPNN may be unavailable"
  pip install -e "${LASERMPNN_REPO}" >/dev/null 2>&1 || \
    pip install numpy scipy biopython >/dev/null 2>&1 || true
  deactivate
  [[ -x "${LASERMPNN_VENV}/bin/python" && -d "${LASERMPNN_REPO}" ]] \
    && state lasermpnn ok "LASErMPNN (CPU)" || state lasermpnn missing "install incomplete"
else
  state lasermpnn skipped "not requested"
fi

# ---- OpenFold-3-MLX (optional predictor) ----
if [[ "${WITH_OPENFOLD3}" -eq 1 ]]; then
  step openfold3 72 "Installing OpenFold-3 (MLX kernels) — downloading ~2 GB checkpoint"
  if [[ ! -d "${OPENFOLD_REPO}" ]]; then
    git clone https://github.com/latent-spacecraft/openfold-3-mlx.git "${OPENFOLD_REPO}" || fail "openfold-3-mlx clone failed."
  fi
  [[ -d "${OPENFOLD_VENV}" ]] || "${PYTHON_BIN}" -m venv "${OPENFOLD_VENV}" || fail "OpenFold venv creation failed."
  source "${OPENFOLD_VENV}/bin/activate"
  pip install --upgrade pip >/dev/null || fail "pip upgrade failed (OpenFold)."
  pip install torch==2.6.0 >/dev/null || fail "torch install failed (OpenFold)."
  pip install -e "${OPENFOLD_REPO}" >/dev/null || fail "openfold-3-mlx install failed."
  OPENFOLD_CHECKPOINT_PATH="${OPENFOLD_CACHE:-$HOME/.openfold3}/of3_ft3_v1.pt"
  python - "${OPENFOLD_CHECKPOINT_PATH}" <<'PY' || fail "OpenFold checkpoint download failed."
import pathlib, sys
import boto3
from botocore import UNSIGNED
from botocore.config import Config

target = pathlib.Path(sys.argv[1]).expanduser()
target.parent.mkdir(parents=True, exist_ok=True)
bucket, key = "openfold", "openfold3_params/of3_ft3_v1.pt"
s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
remote_size = int(s3.head_object(Bucket=bucket, Key=key)["ContentLength"])
if target.exists() and target.stat().st_size == remote_size:
    print(f"  have OpenFold checkpoint: {target}"); raise SystemExit(0)
tmp = target.with_suffix(target.suffix + ".part")
tmp.unlink(missing_ok=True)
print(f"  downloading OpenFold checkpoint ({remote_size / (1024**3):.2f} GB)")
s3.download_file(bucket, key, str(tmp))
if tmp.stat().st_size != remote_size:
    tmp.unlink(missing_ok=True)
    raise RuntimeError("OpenFold checkpoint download incomplete")
tmp.replace(target)
print(f"  OpenFold checkpoint ready: {target}")
PY
  deactivate
  state openfold3 ok "OpenFold-3-MLX"
else
  state openfold3 skipped "not requested"
fi

# ---- AlphaFold 3 (optional predictor; weights are the user's responsibility) ----
if [[ "${WITH_ALPHAFOLD3}" -eq 1 ]]; then
  step alphafold3 84 "Installing AlphaFold 3 (compiles C++ dependencies — this is slow)"
  ensure_uv
  if [[ ! -d "${ALPHAFOLD3_REPO}" ]]; then
    git clone --branch v3.0.4 https://github.com/google-deepmind/alphafold3.git "${ALPHAFOLD3_REPO}" \
      || fail "AlphaFold 3 clone failed."
  fi
  [[ -d "${ALPHAFOLD3_VENV}" ]] || "${UV_BIN}" venv "${ALPHAFOLD3_VENV}" --python 3.12 \
    || fail "AlphaFold 3 venv creation failed."
  # Cap compile parallelism so a design run in progress keeps its CPU and RAM.
  CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2 \
    "${UV_BIN}" pip install --python "${ALPHAFOLD3_VENV}/bin/python" "${ALPHAFOLD3_REPO}" >/dev/null \
    || fail "AlphaFold 3 install failed."
  # The JAX IntelliFold runner reuses AF3's inference engine, so its wrapper
  # lives in this environment while PyTorch IntelliFold stays separate.
  "${UV_BIN}" pip install --python "${ALPHAFOLD3_VENV}/bin/python" \
    --editable "${INTELLIFOLD_REPO}" --no-deps >/dev/null 2>&1 || true
  if [[ -x "${ALPHAFOLD3_VENV}/bin/build_data" ]]; then
    "${ALPHAFOLD3_VENV}/bin/build_data" >/dev/null || fail "AlphaFold 3 chemical component build failed."
  fi
  mkdir -p "${ALPHAFOLD3_MODEL_DIR}"
  if [[ -f "${ALPHAFOLD3_MODEL_DIR}/af3.bin" ]]; then
    state alphafold3 ok "AlphaFold 3 with weights"
  else
    # Not a failure: the environment is usable, the weights are gated by Google's
    # terms and cannot be fetched automatically. The app surfaces this state.
    state alphafold3 missing "environment ready — place af3.bin at ${ALPHAFOLD3_MODEL_DIR}/af3.bin"
  fi
else
  state alphafold3 skipped "not requested"
fi

# ---- IntelliFold JAX/MPS backend (optional speed path) ----
if [[ "${WITH_INTELLIFOLD_JAX}" -eq 1 ]]; then
  step intellifold_jax 92 "Converting IntelliFold v2-flash to the JAX/MPS backend"
  FLASH_PT="${HOME}/.intellifold/intellifold_v2_flash.pt"
  if [[ ! -f "${FLASH_PT}" ]]; then
    state intellifold_jax missing "PyTorch v2-flash checkpoint absent — run one IntelliFold prediction first"
  else
    mkdir -p "${INTELLIFOLD_JAX_MODEL_DIR}"
    PYTHONPATH="${INTELLIFOLD_REPO}" "${INTELLIFOLD_VENV}/bin/python" -m intellifold.convert_flash \
      --schema "${INTELLIFOLD_REPO}/intellifold/af3_schema.pkl" \
      --flash-pt "${FLASH_PT}" \
      --out-dir "${INTELLIFOLD_JAX_MODEL_DIR}" >/dev/null 2>&1 \
      && state intellifold_jax ok "JAX/MPS v2-flash" \
      || state intellifold_jax missing "conversion failed — PyTorch backend remains available"
  fi
else
  state intellifold_jax skipped "not requested"
fi

# ---- RFdiffusion3 (optional backbone generator) ----
if [[ "${WITH_RFD3}" -eq 1 ]]; then
  step rfd3 96 "Installing RFdiffusion3 (MLX)"
  if [[ ! -d "${RFD3_ROOT}" ]]; then
    # The MLX port is the upstream this workflow extends. None of the campaign
    # orchestrators, ligand preparation or predictor adapters are in it -- those
    # arrive from the overlay below, which the app stages out of its own bundle.
    git clone https://github.com/javierbq/rfd3-mlx.git "${RFD3_ROOT}" >/dev/null 2>&1 \
      || state rfd3 missing "could not clone the RFdiffusion3 MLX port"
  fi

  # Apply the overlay before installing: install_rfd3.sh calls scripts that only
  # exist because of it, so a clean clone fails without this.
  if [[ -d "${STUDIO_RFD3_OVERLAY}" && -d "${RFD3_ROOT}" ]]; then
    mkdir -p "${RFD3_ROOT}/scripts"
    cp -f "${STUDIO_RFD3_OVERLAY}"/scripts/*.py "${RFD3_ROOT}/scripts/" 2>/dev/null || true
    for extra in milestone0_oracle.py export_weights.py install_rfd3.sh \
                 requirements-rfd3.txt rfd3_env.sh; do
      [[ -f "${STUDIO_RFD3_OVERLAY}/${extra}" ]] && cp -f "${STUDIO_RFD3_OVERLAY}/${extra}" "${RFD3_ROOT}/"
    done
    [[ -d "${STUDIO_RFD3_OVERLAY}/assets" ]] && cp -R "${STUDIO_RFD3_OVERLAY}/assets/." "${RFD3_ROOT}/assets/" 2>/dev/null
    chmod 755 "${RFD3_ROOT}"/scripts/*.py "${RFD3_ROOT}"/*.sh 2>/dev/null || true
    [[ -f "${STUDIO_RFD3_OVERLAY}/OVERLAY_VERSION" ]] && \
      cp -f "${STUDIO_RFD3_OVERLAY}/OVERLAY_VERSION" "${RFD3_ROOT}/.studio_overlay_version"
    echo "  applied the RFdiffusion3 script overlay"
  fi

  if [[ -x "${RFD3_ROOT}/install_rfd3.sh" ]]; then
    bash "${RFD3_ROOT}/install_rfd3.sh" --download-weights >/dev/null 2>&1 \
      && state rfd3 ok "RFdiffusion3 MLX" \
      || state rfd3 missing "install_rfd3.sh failed — see the log"
  else
    state rfd3 missing "no RFdiffusion3 checkout at ${RFD3_ROOT}"
  fi
else
  state rfd3 skipped "not requested"
fi

step done 100 "Setup complete"
echo "NHDONE|ok"
