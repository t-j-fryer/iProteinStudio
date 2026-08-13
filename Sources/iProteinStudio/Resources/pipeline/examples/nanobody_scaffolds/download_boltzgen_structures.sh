#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/boltzgen_raw"
BASE_URL="https://raw.githubusercontent.com/HannesStark/boltzgen/main/example/nanobody_scaffolds"

mkdir -p "${OUT_DIR}"

files=(
  "7eow.cif"
  "7eow.yaml"
  "7xl0.cif"
  "7xl0.yaml"
  "8coh.cif"
  "8coh.yaml"
  "8z8v.cif"
  "8z8v.yaml"
  "gontivimab.cif"
  "gontivimab.yaml"
  "isecarosmab.cif"
  "isecarosmab.yaml"
  "sonelokimab.cif"
  "sonelokimab.yaml"
)

for file in "${files[@]}"; do
  echo "Downloading ${file}"
  curl -L --fail --retry 3 --retry-delay 2 \
    "${BASE_URL}/${file}" \
    -o "${OUT_DIR}/${file}"
done

echo "BoltzGen scaffold files written to ${OUT_DIR}"
