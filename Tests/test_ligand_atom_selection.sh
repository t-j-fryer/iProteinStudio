#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ATOM_TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/studio-atom-ui.XXXXXX")"
trap 'rm -rf "$ATOM_TEST_ROOT"' EXIT
swiftc -module-cache-path "${CLANG_MODULE_CACHE_PATH:-$ATOM_TEST_ROOT/modules}" -parse-as-library \
  "$ROOT/Sources/iProteinStudio/Models/NISERequest.swift" \
  "$ROOT/Sources/iProteinStudio/Views/NISE/NISEAtomTargetingView.swift" \
  "$ROOT/Sources/iProteinStudio/Views/Structure/LigandAtomPicker.swift" \
  "$ROOT/Tests/LigandAtomSelectionHarness.swift" -o "$ATOM_TEST_ROOT/atom-ui"
"$ATOM_TEST_ROOT/atom-ui" "$ROOT"
