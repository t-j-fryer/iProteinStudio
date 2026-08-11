#!/usr/bin/env bash
# NanoHunter Studio pipeline setup.
#
# Installs only the backends the app uses: Boltz (design predictor),
# IntelliFold (post predictor), LigandMPNN family (+AbMPNN weights), and AntiFold.
# OpenFold and the Jupyter kernel are intentionally excluded.
#
# Emits machine-parseable progress on stdout so the app can render a friendly
# setup wizard:
#   NHSTEP|<key>|<0-100 pct>|<human message>
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

SRC_DIR="${NANOHUNTER_ROOT}/src"
BOLTZ_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_boltz"
LIGAND_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_ligandmpnn"
ANTIFOLD_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_antifold"
INTELLIFOLD_VENV="${NANOHUNTER_ROOT}/venvs/${VENV_PREFIX}_intellifold"
LIGANDMPNN_REPO="${SRC_DIR}/LigandMPNN"
ANTIFOLD_REPO="${SRC_DIR}/AntiFold"
INTELLIFOLD_REPO="${SRC_DIR}/IntelliFold"

step() { echo "NHSTEP|$1|$2|$3"; }
fail() { echo "NHFAIL|$1"; exit 1; }

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

mkdir -p "${NANOHUNTER_ROOT}"/{venvs,src,examples,output}

step python 2 "Preparing Python environments"
command -v git >/dev/null 2>&1 || fail "git not found. Install Xcode Command Line Tools: xcode-select --install"
ensure_python 3.11 PYTHON_BIN
ensure_python 3.10 ANTIFOLD_PYTHON_BIN
ensure_python 3.12 INTELLIFOLD_PYTHON_BIN

# ---- Boltz (design predictor) ----
step boltz 10 "Installing Boltz design engine"
[[ -d "${BOLTZ_VENV}" ]] || "${PYTHON_BIN}" -m venv "${BOLTZ_VENV}" || fail "Boltz venv creation failed."
source "${BOLTZ_VENV}/bin/activate"
pip install --upgrade pip >/dev/null || fail "pip upgrade failed (Boltz)."
pip install torch >/dev/null || fail "torch install failed (Boltz)."
pip install boltz >/dev/null || fail "boltz install failed."
deactivate

# ---- LigandMPNN family (+ AbMPNN weights) ----
step ligandmpnn 35 "Installing sequence designers (ProteinMPNN / SolubleMPNN / LigandMPNN / AbMPNN)"
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
step weights 50 "Downloading model weights (ProteinMPNN / SolubleMPNN / LigandMPNN / AbMPNN)"
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

# ---- AntiFold (antibody-aware designer, default) ----
step antifold 70 "Installing AntiFold (antibody-aware designer)"
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

# ---- IntelliFold (post predictor) ----
step intellifold 85 "Installing IntelliFold post-prediction engine"
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

step done 100 "Setup complete"
echo "NHDONE|ok"
