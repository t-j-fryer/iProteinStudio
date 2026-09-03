#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TILE="${ROOT}/Sources/iProteinStudio/Views/Dashboard/DesignTile.swift"
GRID="${ROOT}/Sources/iProteinStudio/Views/Dashboard/StructuresGridView.swift"
HITS="${ROOT}/Sources/iProteinStudio/Views/Dashboard/HitsGalleryView.swift"
RESULTS="${ROOT}/Sources/iProteinStudio/Views/RunResultsView.swift"
GROUPED="${ROOT}/Sources/iProteinStudio/Views/GroupedRunResultsView.swift"
WATCHER="${ROOT}/Sources/iProteinStudio/Core/MetricsWatcher.swift"
LIVE="${ROOT}/Sources/iProteinStudio/Views/Dashboard/LiveDashboardView.swift"
FORM="${ROOT}/Sources/iProteinStudio/Views/NewRun/DesignFormView.swift"

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
rg -q 'LiveGroupedRunResultsPane' "${LIVE}" \
  || fail "live Structures/Hits tabs do not share the durable grouped browser"
rg -q 'Structures and scores' "${GROUPED}" \
  || fail "grouped browser does not compare related structures and scores"
rg -q 'artifactRole' "${GROUPED}" \
  || fail "grouped browser is not organised by scientific artifact role"
rg -q 'CSVTable.rows' "${WATCHER}" \
  || fail "live post-check parser still depends on positional CSV columns"
rg -q 'savedHitVerdict: boolean' "${WATCHER}" \
  || fail "live Hits tab is not using the saved multi-filter verdict"
! rg -q 'selection: \$request\.speedMode|SpeedMode\.allCases|accessibilityLabel\("Scheduling mode"\)' "${FORM}" \
  || fail "iterative scheduling is still exposed as an Advanced form preference"
rg -q 'Automatic scheduling: one resident predictor stays loaded' "${FORM}" \
  || fail "the main run form does not explain automatic model residency"
rg -q 'Protenix v2 is loaded once per cycle' "${FORM}" \
  || fail "the main run form does not explain Protenix v2's measured exception"
rg -q 'Guide target fold with PDB/CIF' "${FORM}" \
  || fail "ordinary target-fold guidance is not visible in the protein form"
! rg -q 'Keep target coordinates close to the template' "${FORM}" \
  || fail "unsafe strong target restraint is still exposed"
rg -q 'Binder chain A is never templated, and independent checks remain untemplated' "${FORM}" \
  || fail "the form does not disclose the blind validation boundary"

echo "PASS iterative results UI contract"
