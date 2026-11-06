#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPATIAL_TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/studio-spatial-ui.XXXXXX")"
trap 'rm -rf "$SPATIAL_TEST_ROOT"' EXIT
swiftc -module-cache-path "$SPATIAL_TEST_ROOT/modules" -parse-as-library \
  "$ROOT/Sources/iProteinStudio/Views/Structure/LigandSpatialViewer.swift" \
  "$ROOT/Tests/LigandSpatialViewerHarness.swift" -o "$SPATIAL_TEST_ROOT/spatial-ui"
"$SPATIAL_TEST_ROOT/spatial-ui" "$ROOT" "$1" "${2:-/tmp/studio-spatial-viewer.png}"
