#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${1:-${ROOT}/build/iProteinStudio.app}"
BUNDLE="${APP}/Contents/Resources/iProteinStudioResources"

fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -d "${APP}" ]] || fail "packaged app does not exist: ${APP}"
[[ -d "${BUNDLE}" ]] \
  || fail "SwiftPM resource payload is missing from Contents/Resources"
[[ -s "${BUNDLE}/pipeline/PIPELINE_VERSION" ]] \
  || fail "SwiftPM resource bundle is missing its pipeline sentinel"
[[ -s "${BUNDLE}/pipeline/scripts/storage_policy.py" ]] \
  || fail "SwiftPM resource bundle is missing the lossless storage policy"
[[ ! -d "${APP}/iProteinStudio_iProteinStudio.bundle" ]] \
  || fail "resource bundle is incorrectly placed at the sealed app root"

rg -q 'bundledResource\("pipeline"\)' "${ROOT}/Sources/iProteinStudio/Core/AppPaths.swift" \
  || fail "AppPaths does not use the packaged-resource resolver"

if strings "${APP}/Contents/MacOS/iProteinStudio" | grep -F "${ROOT}" >/dev/null; then
  fail "packaged executable contains the build machine's absolute repository path"
fi

codesign --verify --deep --strict "${APP}" \
  || fail "packaged app signature is invalid"

echo "PASS packaged SwiftPM resource bundle contract"
