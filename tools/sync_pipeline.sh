#!/usr/bin/env bash
# Refresh the vendored NanoHunter pipeline assets from an upstream checkout.
#
# Studio ships a copy of the NanoHunter runner and its helper scripts inside the
# app bundle, so the app is self-contained at runtime and does not depend on the
# NanoHunter source tree existing on the user's machine. That copy goes stale
# silently, which once left the app ~1,250 lines behind upstream and unable to
# express any of the optimisation work (lab_book/0001).
#
# This script makes the refresh reproducible and records exactly which upstream
# commit was vendored, in Resources/pipeline/PIPELINE_VERSION.
#
#   ./tools/sync_pipeline.sh [/path/to/NanoHunter]
#
# Defaults to ../NanoHunter, then /Users/thomasfryer/NanoHunter.
set -euo pipefail

STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="${STUDIO_ROOT}/Sources/NanoHunterStudio/Resources/pipeline"

UPSTREAM="${1:-}"
if [[ -z "${UPSTREAM}" ]]; then
  for candidate in "${STUDIO_ROOT}/../NanoHunter" "${HOME}/NanoHunter"; do
    [[ -f "${candidate}/nanohunter_run.sh" ]] && { UPSTREAM="$(cd "${candidate}" && pwd)"; break; }
  done
fi
[[ -n "${UPSTREAM}" && -f "${UPSTREAM}/nanohunter_run.sh" ]] \
  || { echo "error: no NanoHunter checkout found. Pass its path explicitly." >&2; exit 1; }

echo "Vendoring from ${UPSTREAM}"

# Everything ${REPO_ROOT}/… the runner reaches for at execution time. Keep this
# list in sync with:  grep -oE '\$\{REPO_ROOT\}/[A-Za-z0-9_./-]+' nanohunter_run.sh
FILES=(
  nanohunter_run.sh
  motif_scaffolding_helper.py
  scripts/nanobody_cdrs.py
  scripts/sample_antifold_positions.py
  scripts/alphafold3_adapter.py          # AF3 predictor backend
  scripts/compute_throughput_profile.py  # device calibration -> schedule profile
  scripts/merge_openfold_queries.py      # OpenFold-3 native batching
  scripts/rewrite_a3m_query.py           # MSA query-match safeguard
  scripts/lasermpnn_prepare_input.py     # not exposed in the UI; runner references it
  scripts/patch_intellifold_mps.py       # skips CUDA-only cleanup on MPS (setup_pipeline.sh)
  scripts/repair_intellifold_jax_cifs.py # fixes NUL-padded model id in converted JAX CIFs
  scripts/calibrate_device_throughput.py # opt-in per-machine schedule calibration
  scripts/openfold_query_json.py         # OpenFold-3 query JSON (extracted from the runner)
  scripts/openfold_runner_yaml.py        # OpenFold-3 runner YAML (extracted from the runner)
  examples/NanoHunter_nanobody.yaml
  examples/aCbx_bind.yaml
  examples/nanobody_scaffolds/catalog.tsv
)

# Scaffold templates + the JSON/YAML examples the app's own forms rely on.
GLOBS=(
  'examples/nanobody_scaffolds/*.yaml'
  'examples/nanobody_scaffolds/download_boltzgen_structures.sh'
)

copy() {
  local rel="$1" src="${UPSTREAM}/$1" dest="${VENDOR}/$1"
  [[ -f "${src}" ]] || { echo "  MISSING upstream: ${rel}" >&2; return 1; }
  mkdir -p "$(dirname "${dest}")"
  if [[ -f "${dest}" ]] && cmp -s "${src}" "${dest}"; then
    echo "  unchanged  ${rel}"
  else
    cp "${src}" "${dest}"
    echo "  updated    ${rel}"
  fi
}

missing=0
for rel in "${FILES[@]}"; do copy "${rel}" || missing=1; done
for glob in "${GLOBS[@]}"; do
  for src in "${UPSTREAM}"/${glob}; do
    [[ -f "${src}" ]] || continue
    copy "${src#"${UPSTREAM}"/}" || missing=1
  done
done

chmod 755 "${VENDOR}/nanohunter_run.sh" "${VENDOR}/setup_pipeline.sh"

# Preserve Studio-authored files that must never be overwritten by upstream.
# setup_pipeline.sh is ours: it installs only the backends the app exposes and
# emits NHSTEP/NHDONE/NHFAIL progress markers the setup wizard parses.

COMMIT="$(git -C "${UPSTREAM}" rev-parse HEAD 2>/dev/null || echo unknown)"
DESCRIBE="$(git -C "${UPSTREAM}" log -1 --format='%h %ad %s' --date=short 2>/dev/null || echo unknown)"
DIRTY=""
git -C "${UPSTREAM}" diff --quiet 2>/dev/null || DIRTY=" (working tree dirty — vendored copy may not match any commit)"

cat > "${VENDOR}/PIPELINE_VERSION" <<EOF
# Provenance of the vendored NanoHunter pipeline. Regenerate with tools/sync_pipeline.sh.
upstream_path:   ${UPSTREAM}
upstream_commit: ${COMMIT}${DIRTY}
upstream_head:   ${DESCRIBE}
vendored_on:     $(date -u '+%Y-%m-%dT%H:%M:%SZ')
runner_lines:    $(wc -l < "${VENDOR}/nanohunter_run.sh" | tr -d ' ')
runner_sha256:   $(shasum -a 256 "${VENDOR}/nanohunter_run.sh" | awk '{print $1}')
EOF

echo
cat "${VENDOR}/PIPELINE_VERSION"
[[ "${missing}" -eq 0 ]] || { echo; echo "warning: some files were missing upstream (see above)." >&2; exit 1; }
