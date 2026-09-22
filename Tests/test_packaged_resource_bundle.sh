#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${1:-${ROOT}/build/iProteinStudio.app}"
BUNDLE="${APP}/Contents/Resources/iProteinStudioResources"

fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -d "${APP}" ]] || fail "packaged app does not exist: ${APP}"
[[ -d "${BUNDLE}" ]] \
  || fail "SwiftPM resource payload is missing from Contents/Resources"
[[ -s "${BUNDLE}/pipeline/PIPELINE_VERSION" ]] \
  || fail "SwiftPM resource bundle is missing its pipeline sentinel"
[[ -s "${BUNDLE}/pipeline/scripts/storage_policy.py" ]] \
  || fail "SwiftPM resource bundle is missing the lossless storage policy"
for resource in prediction_resume.py resident_predictor.py validate_prediction_geometry.py runtime_package.py runtime_view.py engine_registry.py engine_registry.json engine_adapters.py setup_portable.py runtime_releases.json runtime_assets.json; do
  cmp -s "${BUNDLE}/pipeline/scripts/${resource}" "${ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/${resource}" \
    || fail "prediction resume resource is missing or differs from source: ${resource}"
done
[[ -s "${BUNDLE}/pipeline/examples/nanobody_scaffolds/sources/3eak_provenance.json" ]] \
  || fail "resource bundle is missing the 3EAK scaffold provenance"
rg -q '^3eak_nbbcii10_fgla' "${BUNDLE}/pipeline/examples/nanobody_scaffolds/catalog.tsv" \
  || fail "resource bundle is missing the 3EAK scaffold catalog entry"
[[ -s "${BUNDLE}/pipeline/scripts/prepare_boltz_template.py" ]] \
  || fail "resource bundle is missing the Boltz target-template normalizer"
for resource in download_verified.py install_components.sh abmpnn_sources.json; do
  [[ -s "${BUNDLE}/pipeline/scripts/${resource}" ]] || fail "missing installer recovery resource: ${resource}"
  cmp -s "${BUNDLE}/pipeline/scripts/${resource}" "${ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/${resource}" \
    || fail "installer recovery resource differs from the current source: ${resource}"
done
[[ -s "${BUNDLE}/pipeline/scripts/apple_build_tools.sh" ]] \
  || fail "resource bundle is missing the Apple compiler preflight"
[[ -s "${BUNDLE}/pipeline/scripts/prediction_templates.py" ]] \
  || fail "resource bundle is missing the Predict template adapter"
[[ -s "${BUNDLE}/pipeline/scripts/prepare_intellifold_template.py" ]] \
  || fail "resource bundle is missing the IntelliFold target-template adapter"
[[ -s "${BUNDLE}/pipeline/scripts/intellifold_user_template.py" ]] \
  || fail "resource bundle is missing the IntelliFold local-template policy"
[[ -s "${BUNDLE}/pipeline/scripts/secondary_structure_control.py" ]] \
  || fail "resource bundle is missing the iterative secondary-structure prior helper"
[[ -s "${BUNDLE}/pipeline/scripts/nise/campaign.py" ]] \
  || fail "resource bundle is missing the ligand NISE campaign"
for resource in partial_noising.py search_policy.py contract.py nise_run.py psichic_screen.py psichic_worker.py psichic_contract.py psichic_esm.py psichic_assets.json screening_registry.py; do
  cmp -s "${BUNDLE}/pipeline/scripts/nise/${resource}" "${ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/nise/${resource}" \
    || fail "NISE sampling resource is missing or differs from source: ${resource}"
done
[[ -s "${BUNDLE}/pipeline/mcp/schemas/nise-v1.json" ]] \
  || fail "resource bundle is missing the ligand NISE request schema"
[[ -s "${BUNDLE}/pipeline/scripts/nise/rfd3_initial.py" ]] \
  || fail "resource bundle is missing the NISE RFdiffusion3 adapter"
[[ -s "${BUNDLE}/rfd3_overlay/scripts/rfd3_resume.py" ]] \
  || fail "resource bundle is missing the audited RFdiffusion3 batch helper"
for resource in ligand_atoms.py atom_geometry.py nesso_worker.py nesso_screen.py nesso_contract.py setup_nesso.py ligand_screening.py \
                nesso_assets/protocol.json nesso_assets/requirements.lock nesso_assets/nesso_mps.patch nesso_assets/LICENSE; do
  [[ -s "${BUNDLE}/pipeline/scripts/nise/${resource}" ]] || fail "missing NESSO resource: ${resource}"
done
[[ -s "${BUNDLE}/pipeline/mcp/server.py" ]] \
  || fail "resource bundle is missing the MCP server"
[[ "$(tr -d '[:space:]' < "${BUNDLE}/pipeline/mcp/MCP_VERSION")" == "$(tr -d '[:space:]' < "${ROOT}/Sources/iProteinStudio/Resources/pipeline/mcp/MCP_VERSION")" ]] \
  || fail "resource bundle MCP contract differs from the release source"
[[ -s "${BUNDLE}/pipeline/mcp/remote_server.py" ]] \
  || fail "resource bundle is missing the authenticated remote MCP transport"
[[ -s "${BUNDLE}/pipeline/mcp/remote_gateway.py" ]] \
  || fail "resource bundle is missing the remote MCP lifecycle controller"
[[ -s "${BUNDLE}/pipeline/mcp/schemas/prediction-v1.json" ]] \
  || fail "resource bundle is missing the MCP request schemas"
[[ -s "${BUNDLE}/pipeline/mcp/schemas/target-prepare-v1.json" ]] \
  || fail "resource bundle is missing the MCP target-preparation schema"
[[ -s "${BUNDLE}/examples/p53_mdm2/1YCR.pdb" ]] \
  || fail "resource bundle is missing the p53-MDM2 RFdiffusion3 example"
[[ -s "${BUNDLE}/rfd3_overlay/OVERLAY_VERSION" ]] \
  || fail "resource bundle is missing the RFdiffusion3 overlay receipt"
[[ ! -d "${APP}/iProteinStudio_iProteinStudio.bundle" ]] \
  || fail "resource bundle is incorrectly placed at the sealed app root"

rg -q 'bundledResource\("pipeline"\)' "${ROOT}/Sources/iProteinStudio/Core/AppPaths.swift" \
  || fail "AppPaths does not use the packaged-resource resolver"

if strings "${APP}/Contents/MacOS/iProteinStudio" | grep -F "${ROOT}" >/dev/null; then
  fail "packaged executable contains the build machine's absolute repository path"
fi

codesign --verify --deep --strict "${APP}" \
  || fail "packaged app signature is invalid"

echo "PASS packaged SwiftPM resource bundle contract"
