#!/usr/bin/env bash
# Vendor the RFdiffusion3 script layer into the app bundle.
#
# A fresh clone of the upstream MLX port contains none of this: the campaign
# orchestrators, the ligand preparation, the predictor adapters and the length
# binning are all work that lives on top of it. Without them a new user gets an
# RFdiffusion3 checkout that cannot run a single thing Studio offers.
#
# So the overlay ships inside the app and is applied over the checkout on install
# and on every launch. That also means updating this repo updates users:
# re-staging is what carries a fix to a machine that already installed.
#
#   ./tools/sync_rfd3.sh [/path/to/RFD3]
set -euo pipefail

STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="${STUDIO_ROOT}/Sources/NanoHunterStudio/Resources/rfd3_overlay"

UPSTREAM="${1:-}"
if [[ -z "${UPSTREAM}" ]]; then
  for candidate in "${HOME}/RFD3" "${HOME}/.nanohunterstudio/rfd3"; do
    [[ -d "${candidate}/scripts" ]] && { UPSTREAM="$(cd "${candidate}" && pwd)"; break; }
  done
fi
[[ -n "${UPSTREAM}" && -d "${UPSTREAM}/scripts" ]] \
  || { echo "error: no RFD3 checkout found. Pass its path." >&2; exit 1; }

echo "Vendoring RFdiffusion3 overlay from ${UPSTREAM}"
rm -rf "${VENDOR}"
mkdir -p "${VENDOR}/scripts"

# The whole script layer, plus the fixture builder they all call. Excludes
# __pycache__ and anything campaign-specific.
count=0
for src in "${UPSTREAM}"/scripts/*.py; do
  [[ -f "${src}" ]] || continue
  cp "${src}" "${VENDOR}/scripts/"
  count=$((count + 1))
done
for extra in milestone0_oracle.py export_weights.py install_rfd3.sh requirements-rfd3.txt rfd3_env.sh; do
  [[ -f "${UPSTREAM}/${extra}" ]] && cp "${UPSTREAM}/${extra}" "${VENDOR}/" && count=$((count + 1))
done

# Ligand assets the pinned Foundry build needs: the FHE component is what
# install_rfd3.sh checks for, and its absence makes the install check fail.
if [[ -d "${UPSTREAM}/assets" ]]; then
  mkdir -p "${VENDOR}/assets"
  rsync -a --exclude '__pycache__' "${UPSTREAM}/assets/" "${VENDOR}/assets/" 2>/dev/null \
    || cp -R "${UPSTREAM}/assets/." "${VENDOR}/assets/"
fi

cat > "${VENDOR}/OVERLAY_VERSION" <<EOF
# Provenance of the vendored RFdiffusion3 overlay. Regenerate with tools/sync_rfd3.sh.
source_path:  ${UPSTREAM}
vendored_on:  $(date -u '+%Y-%m-%dT%H:%M:%SZ')
files:        ${count}
checksum:     $(find "${VENDOR}/scripts" -name '*.py' -exec shasum -a 256 {} \; | sort -k2 | shasum -a 256 | awk '{print $1}')
EOF

echo "  ${count} file(s) vendored"
cat "${VENDOR}/OVERLAY_VERSION"
