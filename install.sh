#!/usr/bin/env bash
# Works from a Git checkout or GitHub's extracted source archive.
set -euo pipefail
STUDIO_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec /bin/bash "${STUDIO_SOURCE}/Sources/iProteinStudio/Resources/pipeline/install_cli.sh" "$@"
