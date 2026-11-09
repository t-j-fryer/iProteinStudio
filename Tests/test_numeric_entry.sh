#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NUMERIC_TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/studio-numeric-ui.XXXXXX")"
trap 'rm -rf "$NUMERIC_TEST_ROOT"' EXIT
swiftc -module-cache-path "$NUMERIC_TEST_ROOT/modules" -parse-as-library \
  "$ROOT/Sources/iProteinStudio/Models/NumericInputValue.swift" \
  "$ROOT/Sources/iProteinStudio/Models/Predictor.swift" \
  "$ROOT/Sources/iProteinStudio/Models/EngineRequirementIssue.swift" \
  "$ROOT/Sources/iProteinStudio/Views/Components/NumericTextField.swift" \
  "$ROOT/Sources/iProteinStudio/Views/Components/EditableIntStepper.swift" \
  "$ROOT/Tests/NumericEntryHarness.swift" -o "$NUMERIC_TEST_ROOT/numeric-ui"
"$NUMERIC_TEST_ROOT/numeric-ui"
