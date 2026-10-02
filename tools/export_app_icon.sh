#!/usr/bin/env bash
# Recreate the macOS multi-resolution icon from the checked-in selected artwork.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${ROOT}/Sources/iProteinStudio/Resources/Brand/terra-loop.png"
DESTINATION="${ROOT}/Sources/iProteinStudio/Resources/Brand/AppIcon.icns"
ICON_TMP="$(mktemp -d)"
trap 'rm -rf "${ICON_TMP}"' EXIT
ICONSET="${ICON_TMP}/AppIcon.iconset"
mkdir -p "${ICONSET}"
for points in 16 32 128 256 512; do
  sips -z "$points" "$points" "$SOURCE" --out "${ICONSET}/icon_${points}x${points}.png" >/dev/null
  pixels=$((points * 2))
  sips -z "$pixels" "$pixels" "$SOURCE" --out "${ICONSET}/icon_${points}x${points}@2x.png" >/dev/null
done
iconutil --convert icns "$ICONSET" --output "$DESTINATION"
echo "Exported ${DESTINATION}"
