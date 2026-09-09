#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$(mktemp -d "${TMPDIR:-/tmp}/iproteinstudio-apple-tools-contract.XXXXXX")"
trap 'rm -rf "${FIXTURE}"' EXIT
swiftc -module-cache-path "${FIXTURE}/modules" -emit-library -static -emit-module -module-name StudioCore \
  "${ROOT}/Sources/StudioCore/ExecutionLease.swift" \
  -emit-module-path "${FIXTURE}/StudioCore.swiftmodule" -o "${FIXTURE}/libStudioCore.a"
swiftc -module-cache-path "${FIXTURE}/modules" -parse-as-library -I "${FIXTURE}" -L "${FIXTURE}" -lStudioCore \
  "${ROOT}/Sources/iProteinStudio/Models/Predictor.swift" \
  "${ROOT}/Sources/iProteinStudio/Core/PipelineInstaller.swift" \
  "${ROOT}/Tests/AppleBuildToolsInstallerHarness.swift" \
  -o "${FIXTURE}/apple-tools-contract"
"${FIXTURE}/apple-tools-contract"
swiftc -module-cache-path "${FIXTURE}/modules" -parse-as-library \
  "${ROOT}/Sources/iProteinStudio/Core/InstalledRuntime.swift" \
  "${ROOT}/Tests/InstalledRuntimeHarness.swift" -o "${FIXTURE}/installed-runtime-contract"
"${FIXTURE}/installed-runtime-contract"
