#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/.venv"
CKPT="${ROOT}/checkpoints/rfd3_latest.ckpt"
WEIGHTS="${ROOT}/weights/rfd3_core.safetensors"
CKPT_URL="https://files.ipd.uw.edu/pub/rfd3/rfd3_foundry_2025_12_01_remapped.ckpt"
CKPT_SHA="9b3f85923e0d51e9453e15cdd2f8c666e7ce096a60577f57d11bbc54ae6d67c1"
WEIGHTS_SHA="9d84774c3cf50519991493ab1ee3ffa78597c0ce03f5ea2ffcbd4b42cf3b9c75"

DOWNLOAD=0
CHECK_ONLY=0
for arg in "$@"; do
  case "${arg}" in
    --download-weights) DOWNLOAD=1 ;;
    --check) CHECK_ONLY=1 ;;
    *) echo "Unknown option: ${arg}" >&2; exit 2 ;;
  esac
done

check_sha() {
  local file="$1" expected="$2"
  [[ -f "${file}" ]] || return 1
  local actual
  actual="$(shasum -a 256 "${file}" | awk '{print $1}')"
  [[ "${actual}" == "${expected}" ]] || {
    echo "Checksum mismatch: ${file}" >&2
    echo "expected ${expected}" >&2
    echo "actual   ${actual}" >&2
    return 1
  }
}

if [[ "${CHECK_ONLY}" -eq 0 ]]; then
  command -v uv >/dev/null || { echo "Install uv first: https://docs.astral.sh/uv/" >&2; exit 1; }
  [[ -x "${VENV}/bin/python" ]] || uv venv --python 3.12 "${VENV}"
  uv pip install --python "${VENV}/bin/python" -r "${ROOT}/requirements-rfd3.txt"
  env DEBUG=false "${VENV}/bin/python" "${ROOT}/scripts/patch_foundry_rasa.py"
  env DEBUG=false "${VENV}/bin/python" "${ROOT}/scripts/prepare_fluorescein.py" --output-dir "${ROOT}/assets/fluorescein"
fi

if [[ "${DOWNLOAD}" -eq 1 && ! -f "${CKPT}" ]]; then
  mkdir -p "$(dirname "${CKPT}")"
  caffeinate -dimsu curl -fL --retry 3 "${CKPT_URL}" -o "${CKPT}"
fi

if [[ -f "${CKPT}" ]]; then
  check_sha "${CKPT}" "${CKPT_SHA}"
  if [[ ! -f "${WEIGHTS}" && "${CHECK_ONLY}" -eq 0 ]]; then
    env DEBUG=false TOKENIZERS_PARALLELISM=false caffeinate -dimsu \
      "${VENV}/bin/python" "${ROOT}/export_weights.py"
  fi
else
  echo "Checkpoint absent. Re-run with --download-weights." >&2
fi

[[ -x "${VENV}/bin/python" ]] || { echo "Missing environment: ${VENV}" >&2; exit 1; }
env DEBUG=false CCD_MIRROR_PATH="${ROOT}/assets/fluorescein/ccd" "${VENV}/bin/python" - <<'PY'
import mlx.core as mx
import torch
from atomworks.io.utils.ccd import atom_array_from_ccd_code
assert mx.metal.is_available()
assert torch.backends.mps.is_available()
assert len(atom_array_from_ccd_code("FHE")) == 31
print("MLX Metal, PyTorch MPS, and FHE CCD: OK")
PY

check_sha "${CKPT}" "${CKPT_SHA}" && echo "Official checkpoint checksum: OK"
check_sha "${WEIGHTS}" "${WEIGHTS_SHA}" && echo "MLX weight checksum: OK"
echo "RFD3 installation check complete."
