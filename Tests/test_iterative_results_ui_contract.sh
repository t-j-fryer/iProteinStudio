#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TILE="${ROOT}/Sources/iProteinStudio/Views/Dashboard/DesignTile.swift"
GRID="${ROOT}/Sources/iProteinStudio/Views/Dashboard/StructuresGridView.swift"
HITS="${ROOT}/Sources/iProteinStudio/Views/Dashboard/HitsGalleryView.swift"
RESULTS="${ROOT}/Sources/iProteinStudio/Views/RunResultsView.swift"

fail() { echo "FAIL: $*" >&2; exit 1; }

! rg -q 'showInspector' "${TILE}" \
  || fail "tile-local sheet state can orphan a structure inspector during refresh"
rg -q '@Environment\(\\\.dismiss\)' "${TILE}" \
  || fail "structure inspector has no environment-owned close action"
rg -q 'keyboardShortcut\(\.cancelAction\)' "${TILE}" \
  || fail "Escape cannot close the structure inspector"
rg -q '\.sheet\(item: \$selectedPoint\)' "${GRID}" \
  || fail "structures grid does not own the inspector lifecycle"
rg -q '\.sheet\(item: \$selectedPoint\)' "${HITS}" \
  || fail "hits gallery does not own the inspector lifecycle"
rg -q 'optimized design' "${RESULTS}" \
  || fail "results still label cycle-00 structures as designs"

echo "PASS iterative results UI contract"
