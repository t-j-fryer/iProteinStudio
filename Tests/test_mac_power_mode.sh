#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POWER_TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/studio-power.XXXXXX")"
trap 'rm -rf "$POWER_TEST_ROOT"' EXIT
swiftc -module-cache-path "$POWER_TEST_ROOT/modules" -parse-as-library \
 "$ROOT/Sources/iProteinStudio/Models/MacPowerMode.swift" \
 "$ROOT/Sources/iProteinStudio/Core/MacPowerModeService.swift" \
 "$ROOT/Tests/MacPowerModeHarness.swift" -o "$POWER_TEST_ROOT/power-test"
"$POWER_TEST_ROOT/power-test" "$@"
