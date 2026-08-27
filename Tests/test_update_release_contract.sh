#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail() { echo "FAIL: $*" >&2; exit 1; }

bash -n "${REPO_ROOT}/build_app.sh"
bash -n "${REPO_ROOT}/release/release_app.sh"

rg -q 'exact: "2\.9\.2"' "${REPO_ROOT}/Package.swift" \
  || fail "Sparkle is not pinned exactly"
rg -q 'product\(name: "Sparkle"' "${REPO_ROOT}/Package.swift" \
  || fail "the app target does not link Sparkle"
rg -q '@executable_path/\.\./Frameworks' "${REPO_ROOT}/Package.swift" \
  || fail "the app has no runtime search path for its embedded Sparkle framework"
rg -q '<key>SUFeedURL</key>' "${REPO_ROOT}/build_app.sh" \
  || fail "release bundle omits the appcast URL"
rg -q '<key>SUPublicEDKey</key>' "${REPO_ROOT}/build_app.sh" \
  || fail "release bundle omits the Sparkle public key"
rg -q '<key>SUVerifyUpdateBeforeExtraction</key><true/>' "${REPO_ROOT}/build_app.sh" \
  || fail "updates are not verified before extraction"
rg -q 'Automatically check for app updates' \
  "${REPO_ROOT}/Sources/iProteinStudio/Core/AppUpdateService.swift" \
  || fail "automatic update opt-out is not visible"
rg -q 'Never downloaded automatically' \
  "${REPO_ROOT}/Sources/iProteinStudio/Core/AppUpdateService.swift" \
  || fail "engine/update boundary is absent from Settings"
rg -q 'Nothing is downloaded until you choose Install now' \
  "${REPO_ROOT}/Sources/iProteinStudio/Views/Onboarding/ComponentsView.swift" \
  || fail "engine downloads lack a final consent screen"
rg -q 'ApplicationCopyManager' \
  "${REPO_ROOT}/Sources/iProteinStudio/Core/AppUpdateService.swift" \
  || fail "duplicate application copies cannot be identified"
rg -q 'bundle\.bundleIdentifier == bundleID' \
  "${REPO_ROOT}/Sources/iProteinStudio/Core/AppUpdateService.swift" \
  || fail "old-copy removal is not guarded by bundle identity"
rg -q 'IPStudioDistributionBuild' "${REPO_ROOT}/build_app.sh" \
  || fail "distribution copies cannot advise canonical installation"
rg -q 'IPROTEINSTUDIO_SIGNING_IDENTITY' "${REPO_ROOT}/release/release_app.sh" \
  || fail "release script does not require a Developer ID selector"
rg -q 'notarytool submit' "${REPO_ROOT}/release/release_app.sh" \
  || fail "release script does not submit for notarization"
rg -q 'generate_appcast' "${REPO_ROOT}/release/release_app.sh" \
  || fail "release script does not create signed update metadata"
rg -Fq -- '-o "${APPCAST_WORK}/appcast.xml"' "${REPO_ROOT}/release/release_app.sh" \
  || fail "appcast generation can overwrite the public feed from its working directory"
rg -q -- '--account iproteinstudio' "${REPO_ROOT}/release/release_app.sh" \
  || fail "release signing does not use the isolated Keychain account"

[[ "$(tr -d '[:space:]' < "${REPO_ROOT}/release/sparkle_public_key.txt")" != "" ]] \
  || fail "Sparkle public key is empty"

echo "PASS application/engine update contracts"
