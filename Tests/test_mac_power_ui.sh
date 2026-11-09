#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POWER_UI_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/studio-power-ui.XXXXXX")"
trap 'rm -rf "$POWER_UI_ROOT"' EXIT
swiftc -module-cache-path "$POWER_UI_ROOT/modules" -parse-as-library \
 "$ROOT/Sources/iProteinStudio/Models/MacPowerMode.swift" \
 "$ROOT/Sources/iProteinStudio/Core/MacPowerModeService.swift" \
 "$ROOT/Sources/iProteinStudio/Views/Components/MacPowerModeControl.swift" \
 "$ROOT/Tests/MacPowerModePreviewHarness.swift" -o "$POWER_UI_ROOT/power-ui"
"$POWER_UI_ROOT/power-ui" "$1"
"$POWER_UI_ROOT/power-ui" "${1%.png}-high.png" --high
