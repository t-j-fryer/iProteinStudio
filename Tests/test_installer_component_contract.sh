#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh"
PIPELINE="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/iproteinstudio-installer-contract.XXXXXX")"
SOURCE_ROOT="${TEST_ROOT}/existing"
MANAGED_ROOT="${TEST_ROOT}/managed"
trap 'rm -rf "${TEST_ROOT}"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
make_executable() {
  mkdir -p "$(dirname "$1")"
  printf '#!/bin/sh\nexit 0\n' > "$1"
  chmod +x "$1"
}

bash -n "${SETUP}"
help_output="$(bash "${SETUP}" --help)"
printf '%s\n' "${help_output}" | grep -Fq -- '--with-protenix-constraint' \
  || fail "setup help omits the Protenix Constraint install flag"
printf '%s\n' "${help_output}" | grep -Fq 'design-only, no CPU fallback' \
  || fail "setup help omits the constraint checkpoint safety boundary"
[[ -s "${PIPELINE}/patches/protenix_constraint_mps.patch" ]] \
  || fail "bundled Protenix Constraint MPS patch is absent"
[[ -s "${PIPELINE}/patches/protenix_constraint_zero_substructure.patch" ]] \
  || fail "bundled Protenix Constraint zero-substructure patch is absent"
[[ -s "${PIPELINE}/requirements-protenix-constraint-mps-lock.txt" ]] \
  || fail "bundled Protenix Constraint dependency lock is absent"

# --link-existing requires Boltz only as proof that the source is an installed
# NanoHunter root. The constraint component itself is deliberately synthetic:
# this contract exercises wiring and detection without downloading any weights.
make_executable "${SOURCE_ROOT}/venvs/Test_boltz/bin/python"
make_executable "${SOURCE_ROOT}/venvs/Test_protenix_constraint/bin/protenix"
mkdir -p \
  "${SOURCE_ROOT}/src/ProtenixConstraint/protenix/model/modules" \
  "${SOURCE_ROOT}/models/protenix_constraint/checkpoint" \
  "${SOURCE_ROOT}/models/protenix_constraint/common"
printf 'fixture\n' > "${SOURCE_ROOT}/src/ProtenixConstraint/README"
printf 'fixture substructure source\n' > "${SOURCE_ROOT}/src/ProtenixConstraint/protenix/model/modules/embedders.py"
printf 'fixture\n' > "${SOURCE_ROOT}/models/protenix_constraint/checkpoint/protenix_base_constraint_v0.5.0.pt"
printf 'fixture\n' > "${SOURCE_ROOT}/models/protenix_constraint/common/components.cif"
printf 'fixture\n' > "${SOURCE_ROOT}/models/protenix_constraint/common/components.cif.rdkit_mol.pkl"
python3 - \
  "${SOURCE_ROOT}/models/protenix_constraint/install_receipt.json" \
  "${PIPELINE}/patches/protenix_constraint_mps.patch" \
  "${PIPELINE}/patches/protenix_constraint_zero_substructure.patch" \
  "${SOURCE_ROOT}/src/ProtenixConstraint/protenix/model/modules/embedders.py" <<'PY'
import hashlib, json, pathlib, sys
receipt, base, zero, source = map(pathlib.Path, sys.argv[1:])
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
receipt.write_text(json.dumps({
    "patch_sha256": digest(base),
    "zero_substructure_patch_sha256": digest(zero),
    "substructure_source_sha256": digest(source),
    "zero_substructure": "checkpoint-equivalent-single-token-broadcast",
}) + "\n")
PY

# The app stages its bundled pipeline before linking an existing installation.
# Mirror that contract so detection can fingerprint the managed patch payload.
mkdir -p "${MANAGED_ROOT}/patches"
cp "${PIPELINE}/patches/protenix_constraint_mps.patch" \
  "${MANAGED_ROOT}/patches/protenix_constraint_mps.patch"
cp "${PIPELINE}/patches/protenix_constraint_zero_substructure.patch" \
  "${MANAGED_ROOT}/patches/protenix_constraint_zero_substructure.patch"

link_output="$(NANOHUNTER_ROOT="${MANAGED_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${SETUP}" --link-existing "${SOURCE_ROOT}")"
printf '%s\n' "${link_output}" | grep -Fq 'NHSTATE|protenix_constraint|ok|' \
  || fail "linked Protenix Constraint component was not detected as usable"
for rel in \
  venvs/Test_protenix_constraint src/ProtenixConstraint models/protenix_constraint
do
  [[ -L "${MANAGED_ROOT}/${rel}" ]] || fail "reuse omitted ${rel}"
done

materialise_output="$(NANOHUNTER_ROOT="${MANAGED_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${SETUP}" --materialise)"
printf '%s\n' "${materialise_output}" | grep -Fq 'NHSTATE|protenix_constraint|ok|' \
  || fail "materialised Protenix Constraint component was not detected as usable"
for rel in \
  venvs/Test_protenix_constraint src/ProtenixConstraint models/protenix_constraint
do
  [[ -e "${MANAGED_ROOT}/${rel}" && ! -L "${MANAGED_ROOT}/${rel}" ]] \
    || fail "materialisation did not make ${rel} self-contained"
done

echo "PASS installer component contract"
