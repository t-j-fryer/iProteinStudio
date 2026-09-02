#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE="${ROOT}/release/release_app.sh"
BUILDER="${ROOT}/build_app.sh"
UPDATER="${ROOT}/Sources/iProteinStudio/Core/AppUpdateService.swift"

fail() { echo "FAIL: $*" >&2; exit 1; }

bash -n "${RELEASE}"
bash -n "${BUILDER}"

rg -q -- '--unsigned-beta' "${RELEASE}" \
  || fail "release script has no explicit unsigned-beta route"
rg -q 'dirty-local-test' "${RELEASE}" \
  || fail "dirty unsigned builds are not marked non-publishable"
rg -q 'SHA256SUMS\.txt' "${RELEASE}" \
  || fail "unsigned artifacts do not receive a checksum manifest"
rg -q 'SPARKLE_UPDATE_BUILD=true' "${BUILDER}" \
  || fail "trusted beta does not enable Sparkle"
rg -q 'sparkleUpdateBuild && feedIsSecure && keyLooksValid' "${UPDATER}" \
  || fail "Sparkle can start without an explicit verified-update marker"
rg -q 'distributionChannel == "unsigned-beta"' "${UPDATER}" \
  || fail "unsigned beta has no explicit trust explanation"
rg -q 'sparkle:edSignature=' "${RELEASE}" \
  || fail "beta packager does not require an EdDSA-signed update archive"
rg -q -- '--publish-unsigned-beta' "${RELEASE}" \
  || fail "trusted beta has no explicit publishing route"

for document in LICENSE LICENSING.md THIRD_PARTY_NOTICES.md PRIVACY.md SECURITY.md SUPPORT.md \
                docs/INSTALL_UNSIGNED_BETA.md; do
  [[ -s "${ROOT}/${document}" ]] || fail "missing distribution document: ${document}"
done
for license in third_party_licenses/RDKit-LICENSE.txt \
               third_party_licenses/3Dmol-LICENSE.txt; do
  [[ -s "${ROOT}/${license}" ]] || fail "missing embedded licence: ${license}"
done

rg -Fq '"${APP}/Contents/Resources/${RESOURCE_DIRECTORY}"' "${BUILDER}" \
  || fail "packager does not put resources in the sealed app resource directory"
rg -q 'private static let bundledResourcesRoot' "${ROOT}/Sources/iProteinStudio/Core/AppPaths.swift" \
  || fail "packaged resources have no app-aware resolver"
! rg -q 'return Bundle\.module|Bundle\.module\.url' "${ROOT}/Sources/iProteinStudio/Core/AppPaths.swift" \
  || fail "packaged resources still invoke SwiftPM's build-machine fallback"

! rg -q 'spctl --master-disable|xattr -[a-zA-Z]*d.*com\.apple\.quarantine' \
  "${ROOT}/docs/INSTALL_UNSIGNED_BETA.md" "${ROOT}/SECURITY.md" \
  || fail "documentation weakens Gatekeeper instead of using Apple's per-app override"

echo "PASS unsigned beta release contract"
