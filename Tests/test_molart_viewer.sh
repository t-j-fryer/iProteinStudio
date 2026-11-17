#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOLART_TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/studio-molart-ui.XXXXXX")"
trap 'rm -rf "$MOLART_TEST_ROOT"' EXIT
swiftc -module-cache-path "$MOLART_TEST_ROOT/modules" -parse-as-library \
  "$ROOT/Sources/iProteinStudio/Views/Structure/StructureViewer.swift" \
  "$ROOT/Tests/MolartViewerHarness.swift" -o "$MOLART_TEST_ROOT/molart-ui"
"$MOLART_TEST_ROOT/molart-ui" "$ROOT" \
  "$ROOT/Sources/iProteinStudio/Resources/examples/t4_lysozyme/2LZM.pdb" \
  "$ROOT/Sources/iProteinStudio/Resources/examples/t4_lysozyme/2LZM.cif" \
  "${1:-$ROOT/build/molart-native-acceptance}"
