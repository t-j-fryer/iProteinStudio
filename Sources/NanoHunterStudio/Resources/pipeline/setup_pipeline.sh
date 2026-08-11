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
    --link-rfd3)            LINK_RFD3="$2"; shift 2 ;;
    --detect)               DETECT_ONLY=1; shift ;;
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
  if [[ -x "${RFD3_ROOT}/install_rfd3.sh" ]]; then
    bash "${RFD3_ROOT}/install_rfd3.sh" --download-weights >/dev/null 2>&1 \
      && state rfd3 ok "RFdiffusion3 MLX" \
      || state rfd3 missing "install_rfd3.sh failed — see the log"
  else
    state rfd3 missing "no RFD3 checkout at ${RFD3_ROOT}; link an existing one in Settings"
  fi
else
  state rfd3 skipped "not requested"
fi

step done 100 "Setup complete"
echo "NHDONE|ok"
