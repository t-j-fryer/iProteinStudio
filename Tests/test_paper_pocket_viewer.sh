#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POCKET_TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/studio-pocket-ui.XXXXXX")"
trap 'rm -rf "$POCKET_TEST_ROOT"' EXIT
swiftc -module-cache-path "$POCKET_TEST_ROOT/modules" -parse-as-library \
  "$ROOT/Sources/iProteinStudio/Views/Structure/StructureViewer.swift" \
  "$ROOT/Tests/PaperPocketViewerHarness.swift" -o "$POCKET_TEST_ROOT/pocket-ui"
"$POCKET_TEST_ROOT/pocket-ui" "$ROOT" "$1" "$2" "${3:-/tmp/studio-paper-pocket.png}"
