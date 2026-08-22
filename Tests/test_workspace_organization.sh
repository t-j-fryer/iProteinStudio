#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/iproteinstudio-workspace-contract.XXXXXX")"
trap 'rm -rf "${TEST_ROOT}"' EXIT

swiftc \
  "${REPO_ROOT}/Sources/iProteinStudio/Models/WorkspaceOrganization.swift" \
  "${REPO_ROOT}/Tests/WorkspaceOrganizationContractHarness.swift" \
  -o "${TEST_ROOT}/workspace-organization-contract"

"${TEST_ROOT}/workspace-organization-contract"

# These are product-level contracts that the pure naming harness cannot see.
rg -q 'Section\("Library"\)' \
  "${REPO_ROOT}/Sources/iProteinStudio/Views/Projects/ProjectSidebar.swift"
rg -q 'Section\("Workspaces"\)' \
  "${REPO_ROOT}/Sources/iProteinStudio/Views/Projects/ProjectSidebar.swift"
rg -q 'Label\("New Prediction"' \
  "${REPO_ROOT}/Sources/iProteinStudio/Views/Projects/ProjectSidebar.swift"
rg -q 'title: "Rename Workspace"' \
  "${REPO_ROOT}/Sources/iProteinStudio/Views/RootView.swift"
rg -q 'title: "Rename Prediction"' \
  "${REPO_ROOT}/Sources/iProteinStudio/Views/Library/PredictionsLibraryView.swift"

echo "PASS workspace navigation contracts"
