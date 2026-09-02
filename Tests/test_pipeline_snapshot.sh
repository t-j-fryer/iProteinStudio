#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$(mktemp -d "${TMPDIR:-/tmp}/iproteinstudio-snapshot.XXXXXX")"
trap 'rm -rf "${FIXTURE}"' EXIT

swiftc \
  "${ROOT}/Sources/iProteinStudio/Core/AppPaths.swift" \
  "${ROOT}/Tests/PipelineSnapshotContractHarness.swift" \
  -o "${FIXTURE}/snapshot-contract"

IPROTEINSTUDIO_RESOURCE_ROOT="${ROOT}/Sources/iProteinStudio/Resources" \
IPROTEINSTUDIO_TEST_SUPPORT_ROOT="${FIXTURE}/support" \
  "${FIXTURE}/snapshot-contract"
