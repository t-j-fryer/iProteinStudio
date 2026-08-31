#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK="/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk"
CACHE="${TMPDIR:-/tmp}/iproteinstudio-process-runner-module-cache"
BINARY="${TMPDIR:-/tmp}/iproteinstudio-process-runner-contract"
mkdir -p "${CACHE}"

swiftc -sdk "${SDK}" -module-cache-path "${CACHE}" -parse-as-library \
  "${REPO_ROOT}/Sources/iProteinStudio/Core/ProcessRunner.swift" \
  "${REPO_ROOT}/Tests/ProcessRunnerCancellationHarness.swift" \
  -o "${BINARY}"
"${BINARY}"
