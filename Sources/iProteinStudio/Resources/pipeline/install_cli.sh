#!/usr/bin/env bash
# Headless entry point; inference still uses the normal Studio job broker.
set -euo pipefail
SOURCE_RESOURCES="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="${NANOHUNTER_ROOT:-${HOME}/.iproteinstudio}"
STAGE_ONLY=0
DETECT_ONLY=0
SETUP_ARGS=()
usage() {
  cat <<'EOF'
Install iProteinStudio without opening the app (Apple silicon/macOS).

  bash install.sh --base                 Standard design/prediction engines
  bash install.sh --with-boltz           Select engines using Setup's flags
  bash install.sh --with-rfd4 --with-esmfold2-full --with-esmfold2-600
  bash install.sh --stage-only           CLI/MCP and assets; no models
  bash install.sh --detect               Read-only engine detection

  --root PATH       Managed installation (default NANOHUNTER_ROOT or ~/.iproteinstudio)
  --resources PATH  Resource directory from a checkout or extracted app bundle
  --help            Show this help; --setup-help lists all engine selections

No sudo, Homebrew, Git, system Python, compiler or desktop session is required
by this installer. Use --base, --all or explicit --with-* selections to download
models. Repeating the command retries incomplete components. Existing projects,
weights and retained job snapshots are preserved. An active Studio job blocks updates.
EOF
}
fail() { printf 'Studio install: %s\n' "$*" >&2; exit 2; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root|--resources)
      [[ $# -ge 2 && -n "$2" ]] || fail "$1 needs a path."
      if [[ "$1" == --root ]]; then INSTALL_ROOT="$2"; else SOURCE_RESOURCES="$2"; fi
      shift 2 ;;
    --stage-only) STAGE_ONLY=1; shift ;;
    --detect) DETECT_ONLY=1; shift ;;
    --help|-h) usage; exit 0 ;;
    --setup-help) exec /bin/bash "${SOURCE_RESOURCES}/pipeline/setup_pipeline.sh" --help ;;
    --base|--all|--with-boltz|--with-boltz-affinity|--with-antifold|--with-intellifold|--with-intellifold-full|--with-protenix-runtime|--with-protenix-v2|--with-protenix-mini|--with-protenix|--with-protenix-constraint|--with-rfd4|--with-rfd3|--with-esmfold2-full|--with-esmfold2-fast|--with-esmfold2-600|--with-openfold3|--with-abmpnn|--without-abmpnn|--with-lasermpnn|--with-nesso|--with-psichic)
      SETUP_ARGS+=("$1"); shift ;;
    *) fail "Unknown option: $1. Use --help or --setup-help." ;;
  esac
done
[[ -f "${SOURCE_RESOURCES}/pipeline/PIPELINE_VERSION" && -d "${SOURCE_RESOURCES}/rfd3" ]] \
  || fail "Resource payload missing. Run install.sh from a checkout/archive, or use --resources with an extracted app's iProteinStudioResources directory."
[[ "${INSTALL_ROOT}" == /* ]] || INSTALL_ROOT="${PWD}/${INSTALL_ROOT}"
case "${INSTALL_ROOT}" in *[[:space:]]*) fail "Use an installation path without whitespace (Python executable paths must remain runnable)." ;; esac
export NANOHUNTER_ROOT="${INSTALL_ROOT}"
if [[ "${DETECT_ONLY}" == 1 ]]; then
  [[ "${STAGE_ONLY}" == 0 && ${#SETUP_ARGS[@]} == 0 ]] || fail "--detect cannot be combined with installation selections."
  exec /bin/bash "${SOURCE_RESOURCES}/pipeline/setup_pipeline.sh" --detect
fi
# Keep the local beta app's existing runtime isolation contract. Its resources
# are workflow snapshots, not an engine-maintenance distribution.
BUNDLE_INFO="${SOURCE_RESOURCES}/../../Info.plist"
if [[ -f "${BUNDLE_INFO}" ]] \
  && [[ "$(/usr/libexec/PlistBuddy -c 'Print :IPStudioLocalBeta' "${BUNDLE_INFO}" 2>/dev/null || true)" == 1 ]]; then
  fail "Local Beta bundles cannot stage or change shared runtimes. Use a reviewed source checkout or a public distribution bundle."
fi
if [[ "${STAGE_ONLY}" == 1 ]]; then
  [[ ${#SETUP_ARGS[@]} == 0 ]] || fail "Choose --stage-only or engine selections, not both."
  SETUP_ARGS=(--retry-components control)
elif [[ ${#SETUP_ARGS[@]} == 0 ]]; then
  usage
  exit 0
fi
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] \
  || fail "This installer requires native Apple silicon macOS (not Linux or a Rosetta shell)."

# Bootstrap into a private temporary root first. No target installation is changed
# until the Python stager holds the same execution lease as the app and broker.
BOOTSTRAP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/studio-bootstrap.XXXXXX")"
BOOTSTRAP_ROOT="$(cd "${BOOTSTRAP_ROOT}" && pwd -P)"
cleanup() { rm -rf "${BOOTSTRAP_ROOT}"; }
trap cleanup EXIT
BOOTSTRAP_PYTHON="${INSTALL_ROOT}/components/control/current/python/bin/python3"
if [[ ! -x "${BOOTSTRAP_PYTHON}" ]]; then
  NANOHUNTER_ROOT="${BOOTSTRAP_ROOT}" \
    /bin/bash "${SOURCE_RESOURCES}/pipeline/setup_pipeline.sh" --bootstrap-control \
    | tee "${BOOTSTRAP_ROOT}/bootstrap.log"
  BOOTSTRAP_PYTHON="$(awk '/^NHPYTHON\|/ {sub(/^NHPYTHON\|/, ""); print}' "${BOOTSTRAP_ROOT}/bootstrap.log")"
  [[ -x "${BOOTSTRAP_PYTHON}" && "${BOOTSTRAP_PYTHON}" == "${BOOTSTRAP_ROOT}/"* ]] \
    || fail "The pinned Python bootstrap did not return its managed interpreter."
fi
"${BOOTSTRAP_PYTHON}" "${SOURCE_RESOURCES}/pipeline/scripts/stage_assets.py" \
  --resources "${SOURCE_RESOURCES}" --root "${INSTALL_ROOT}" --install -- "${SETUP_ARGS[@]}"
printf '\nStudio CLI: %s/bin/studioctl\nMCP server: %s/bin/studio-mcp --profile read\n' "${INSTALL_ROOT}" "${INSTALL_ROOT}"
