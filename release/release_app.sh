#!/usr/bin/env bash
# Build, sign, notarize and optionally publish a Sparkle-compatible release.
# The Sparkle private key stays in the login Keychain; Apple credentials stay
# in a notarytool Keychain profile. Neither secret is accepted as a file here.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

MODE="${1:---preflight}"
SECOND_ARGUMENT="${2:-}"
ALLOW_DIRTY_BETA=false
if [[ "${MODE}" == "--unsigned-beta" && "${SECOND_ARGUMENT}" == "--allow-dirty" ]]; then
  ALLOW_DIRTY_BETA=true
  SECOND_ARGUMENT=""
fi
VERSION="$(tr -d '[:space:]' < VERSION)"
BUILD_NUMBER="$(tr -d '[:space:]' < BUILD_NUMBER)"
PUBLIC_KEY="$(tr -d '[:space:]' < release/sparkle_public_key.txt)"
SPARKLE_ROOT=".build/artifacts/sparkle/Sparkle"
GENERATE_KEYS="${SPARKLE_ROOT}/bin/generate_keys"
GENERATE_APPCAST="${SPARKLE_ROOT}/bin/generate_appcast"
SIGNING_IDENTITY="${IPROTEINSTUDIO_SIGNING_IDENTITY:-}"
NOTARY_PROFILE="${IPROTEINSTUDIO_NOTARY_PROFILE:-}"
TAG="v${VERSION}"
DIST_DIR="build/release-${VERSION}"
APP="build/iProteinStudio.app"
ARCHIVE_BASENAME="iProteinStudio-${VERSION}"
ZIP_PATH="${DIST_DIR}/${ARCHIVE_BASENAME}.zip"
DMG_PATH="${DIST_DIR}/${ARCHIVE_BASENAME}.dmg"

fail() { echo "ERROR: $*" >&2; exit 2; }

[[ -z "${SECOND_ARGUMENT}" ]] \
  || fail "Usage: release/release_app.sh [--preflight|--build|--publish|--unsigned-beta [--allow-dirty]|--publish-unsigned-beta]"
[[ "${MODE}" == "--preflight" || "${MODE}" == "--build" || "${MODE}" == "--publish" \
   || "${MODE}" == "--unsigned-beta" || "${MODE}" == "--publish-unsigned-beta" ]] \
  || fail "Usage: release/release_app.sh [--preflight|--build|--publish|--unsigned-beta [--allow-dirty]|--publish-unsigned-beta]"
[[ "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9]+)*$ ]] \
  || fail "VERSION is malformed: ${VERSION}"
[[ "${BUILD_NUMBER}" =~ ^[1-9][0-9]*$ ]] || fail "BUILD_NUMBER must be a positive integer."
[[ -n "${PUBLIC_KEY}" ]] || fail "The checked-in Sparkle public key is empty."

if [[ "${MODE}" == "--unsigned-beta" || "${MODE}" == "--publish-unsigned-beta" ]]; then
  [[ -x "${GENERATE_KEYS}" && -x "${GENERATE_APPCAST}" ]] \
    || fail "Sparkle tools are absent. Run: swift package resolve"
  KEYCHAIN_PUBLIC_KEY="$(${GENERATE_KEYS} --account iproteinstudio -p | tr -d '[:space:]')"
  [[ "${KEYCHAIN_PUBLIC_KEY}" == "${PUBLIC_KEY}" ]] \
    || fail "The login-Keychain Sparkle key does not match release/sparkle_public_key.txt."

  DIRTY_STATUS="$(git status --porcelain --untracked-files=all)"
  if [[ -n "${DIRTY_STATUS}" && "${ALLOW_DIRTY_BETA}" != true ]]; then
    fail "Tracked or untracked source changes are present. Commit them, or use --allow-dirty only for a non-publishable second-Mac test artifact."
  fi

  SOURCE_COMMIT="$(git rev-parse HEAD)"
  SOURCE_STATE="clean"
  if [[ -n "${DIRTY_STATUS}" ]]; then
    SOURCE_STATE="dirty-local-test"
  fi
  UNSIGNED_DIST_DIR="build/unsigned-beta-${VERSION}-${BUILD_NUMBER}"
  UNSIGNED_BASENAME="iProteinStudio-${VERSION}-unsigned-beta-apple-silicon"
  UNSIGNED_ZIP="${UNSIGNED_DIST_DIR}/${UNSIGNED_BASENAME}.zip"
  UNSIGNED_DMG="${UNSIGNED_DIST_DIR}/${UNSIGNED_BASENAME}.dmg"
  UNSIGNED_STAGE="${UNSIGNED_DIST_DIR}/dmg-root"
  UNSIGNED_APPCAST_WORK="${UNSIGNED_DIST_DIR}/appcast-work"
  UNSIGNED_APPCAST="${UNSIGNED_DIST_DIR}/appcast.xml"
  UNSIGNED_TAG="v${VERSION}-beta"

  echo "iProteinStudio ${VERSION} (${BUILD_NUMBER}) unsigned beta"
  echo "Source: ${SOURCE_COMMIT} (${SOURCE_STATE})"
  if [[ "${SOURCE_STATE}" != "clean" ]]; then
    echo "WARNING: this artifact is for local cross-Mac testing only and must not be published."
  fi

  IPROTEINSTUDIO_UNSIGNED_BETA=1 IPROTEINSTUDIO_SIGNING_IDENTITY=- \
    /usr/bin/caffeinate -dimsu ./build_app.sh release
  codesign --verify --deep --strict --verbose=2 "${APP}"
  bash Tests/test_packaged_resource_bundle.sh "${APP}"
  codesign -dv --verbose=4 "${APP}" 2>&1 | grep -F 'Signature=adhoc' >/dev/null \
    || fail "Unsigned beta app is not ad-hoc signed."
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :IPStudioDistributionChannel' "${APP}/Contents/Info.plist")" == "unsigned-beta" ]] \
    || fail "Unsigned beta distribution channel is missing."
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :IPStudioDistributionBuild' "${APP}/Contents/Info.plist")" == "true" ]] \
    || fail "Unsigned beta will not show the Applications-folder notice."
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :IPStudioSparkleUpdateBuild' "${APP}/Contents/Info.plist")" == "true" ]] \
    || fail "Unsigned beta does not enable Sparkle's verified update channel."
  [[ "$(lipo -archs "${APP}/Contents/MacOS/iProteinStudio")" == "arm64" ]] \
    || fail "Unsigned beta executable is not Apple-silicon-only arm64."

  rm -rf "${UNSIGNED_DIST_DIR}"
  mkdir -p "${UNSIGNED_DIST_DIR}" "${UNSIGNED_STAGE}"
  /usr/bin/ditto -c -k --sequesterRsrc --keepParent "${APP}" "${UNSIGNED_ZIP}"
  /usr/bin/ditto "${APP}" "${UNSIGNED_STAGE}/iProteinStudio.app"
  ln -s /Applications "${UNSIGNED_STAGE}/Applications"
  cp docs/INSTALL_UNSIGNED_BETA.md "${UNSIGNED_STAGE}/READ ME - UNSIGNED BETA.md"
  cp PRIVACY.md SECURITY.md SUPPORT.md LICENSING.md THIRD_PARTY_NOTICES.md \
    "${UNSIGNED_STAGE}/"
  {
    printf 'iProteinStudio unsigned beta\n'
    printf 'Version: %s\n' "${VERSION}"
    printf 'Build: %s\n' "${BUILD_NUMBER}"
    printf 'Architecture: arm64 (Apple silicon)\n'
    printf 'Minimum macOS: 14.0\n'
    printf 'Source commit: %s\n' "${SOURCE_COMMIT}"
    printf 'Source state: %s\n' "${SOURCE_STATE}"
    printf 'Code signature: ad hoc; not Developer ID signed or Apple notarized\n'
    printf 'Application updates: Sparkle enabled; update archives require the project EdDSA signature\n'
    printf 'Update feed: https://raw.githubusercontent.com/t-j-fryer/iProteinStudio/main/appcast.xml\n'
  } > "${UNSIGNED_STAGE}/BUILD_PROVENANCE.txt"
  cp "${UNSIGNED_STAGE}/BUILD_PROVENANCE.txt" "${UNSIGNED_DIST_DIR}/BUILD_PROVENANCE.txt"
  hdiutil create -quiet -volname "iProteinStudio unsigned beta" \
    -srcfolder "${UNSIGNED_STAGE}" -ov -format UDZO "${UNSIGNED_DMG}"
  rm -rf "${UNSIGNED_STAGE}"

  mkdir -p "${UNSIGNED_APPCAST_WORK}"
  cp "${UNSIGNED_ZIP}" "${UNSIGNED_APPCAST_WORK}/${UNSIGNED_BASENAME}.zip"
  cp CHANGELOG.md "${UNSIGNED_APPCAST_WORK}/${UNSIGNED_BASENAME}.md"
  cp appcast.xml "${UNSIGNED_APPCAST_WORK}/appcast.xml"
  "${GENERATE_APPCAST}" \
    --account iproteinstudio \
    --download-url-prefix "https://github.com/t-j-fryer/iProteinStudio/releases/download/${UNSIGNED_TAG}/" \
    --embed-release-notes \
    -o "${UNSIGNED_APPCAST_WORK}/appcast.xml" \
    "${UNSIGNED_APPCAST_WORK}"
  cp "${UNSIGNED_APPCAST_WORK}/appcast.xml" "${UNSIGNED_APPCAST}"
  rm -rf "${UNSIGNED_APPCAST_WORK}"
  grep -F 'sparkle:edSignature=' "${UNSIGNED_APPCAST}" >/dev/null \
    || fail "Generated beta appcast has no Sparkle EdDSA archive signature."

  (
    cd "${UNSIGNED_DIST_DIR}"
    shasum -a 256 "$(basename "${UNSIGNED_DMG}")" "$(basename "${UNSIGNED_ZIP}")" \
      > SHA256SUMS.txt
  )

  echo "Unsigned beta artifacts are ready in ${UNSIGNED_DIST_DIR}"
  echo "The beta appcast contains a Sparkle EdDSA archive signature."
  echo "Installation instructions: docs/INSTALL_UNSIGNED_BETA.md"
  [[ "${SOURCE_STATE}" == "clean" ]] \
    || echo "Do not publish this dirty-local-test build. Rebuild from a committed clean tree first."

  if [[ "${MODE}" == "--publish-unsigned-beta" ]]; then
    [[ "${SOURCE_STATE}" == "clean" ]] \
      || fail "A dirty local-test beta cannot be published."
    command -v gh >/dev/null || fail "GitHub CLI is required for --publish-unsigned-beta."
    gh auth status >/dev/null || fail "GitHub CLI is not authenticated."
    git rev-parse "${UNSIGNED_TAG}" >/dev/null 2>&1 \
      || git tag -a "${UNSIGNED_TAG}" -m "iProteinStudio ${VERSION} trusted beta"
    git push origin "${UNSIGNED_TAG}"
    if gh release view "${UNSIGNED_TAG}" >/dev/null 2>&1; then
      gh release upload "${UNSIGNED_TAG}" "${UNSIGNED_ZIP}" "${UNSIGNED_DMG}" \
        "${UNSIGNED_DIST_DIR}/SHA256SUMS.txt" "${UNSIGNED_DIST_DIR}/BUILD_PROVENANCE.txt" --clobber
    else
      gh release create "${UNSIGNED_TAG}" "${UNSIGNED_ZIP}" "${UNSIGNED_DMG}" \
        "${UNSIGNED_DIST_DIR}/SHA256SUMS.txt" "${UNSIGNED_DIST_DIR}/BUILD_PROVENANCE.txt" \
        --prerelease --title "iProteinStudio ${VERSION} trusted beta" --notes-file CHANGELOG.md
    fi
    cp "${UNSIGNED_APPCAST}" appcast.xml
    if ! git diff --quiet -- appcast.xml; then
      git add appcast.xml
      git commit -m "Publish iProteinStudio ${VERSION} trusted beta update feed"
    fi
    git push origin main
    echo "Published ${UNSIGNED_TAG}; trusted-beta appcast is live on main."
  fi
  exit 0
fi

[[ -x "${GENERATE_KEYS}" && -x "${GENERATE_APPCAST}" ]] \
  || fail "Sparkle tools are absent. Run: swift package resolve"

KEYCHAIN_PUBLIC_KEY="$(${GENERATE_KEYS} --account iproteinstudio -p | tr -d '[:space:]')"
[[ "${KEYCHAIN_PUBLIC_KEY}" == "${PUBLIC_KEY}" ]] \
  || fail "The login-Keychain Sparkle key does not match release/sparkle_public_key.txt."

echo "iProteinStudio ${VERSION} (${BUILD_NUMBER})"
echo "Sparkle signing key: present and matches the checked-in public key"
echo "Update feed: https://raw.githubusercontent.com/t-j-fryer/iProteinStudio/main/appcast.xml"

if [[ -z "${SIGNING_IDENTITY}" ]]; then
  echo "BLOCKED: set IPROTEINSTUDIO_SIGNING_IDENTITY to an installed 'Developer ID Application: …' identity."
  [[ "${MODE}" == "--preflight" ]] && exit 3
  fail "A Developer ID Application identity is required."
fi
security find-identity -v -p codesigning | grep -F "${SIGNING_IDENTITY}" >/dev/null \
  || fail "Signing identity is not installed or valid: ${SIGNING_IDENTITY}"

if [[ -z "${NOTARY_PROFILE}" ]]; then
  echo "BLOCKED: set IPROTEINSTUDIO_NOTARY_PROFILE to a notarytool Keychain profile name."
  [[ "${MODE}" == "--preflight" ]] && exit 3
  fail "A notarytool Keychain profile is required."
fi
xcrun notarytool history --keychain-profile "${NOTARY_PROFILE}" >/dev/null \
  || fail "notarytool could not use Keychain profile: ${NOTARY_PROFILE}"

echo "Developer ID identity: available"
echo "Notarytool profile: available"
[[ "${MODE}" == "--preflight" ]] && exit 0

[[ -z "$(git status --porcelain --untracked-files=no)" ]] \
  || fail "Tracked files are dirty. Commit the release contents before building."

IPROTEINSTUDIO_SIGNING_IDENTITY="${SIGNING_IDENTITY}" \
  /usr/bin/caffeinate -dimsu ./build_app.sh release
codesign --verify --deep --strict --verbose=2 "${APP}"
bash Tests/test_packaged_resource_bundle.sh "${APP}"

mkdir -p "${DIST_DIR}"
NOTARY_ZIP="${DIST_DIR}/notary-upload.zip"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "${APP}" "${NOTARY_ZIP}"
xcrun notarytool submit "${NOTARY_ZIP}" --keychain-profile "${NOTARY_PROFILE}" --wait
xcrun stapler staple "${APP}"
xcrun stapler validate "${APP}"
rm -f "${NOTARY_ZIP}"

/usr/bin/ditto -c -k --sequesterRsrc --keepParent "${APP}" "${ZIP_PATH}"

DMG_STAGE="${DIST_DIR}/dmg-root"
rm -rf "${DMG_STAGE}"
mkdir -p "${DMG_STAGE}"
/usr/bin/ditto "${APP}" "${DMG_STAGE}/iProteinStudio.app"
ln -s /Applications "${DMG_STAGE}/Applications"
hdiutil create -quiet -volname "iProteinStudio" -srcfolder "${DMG_STAGE}" -ov -format UDZO "${DMG_PATH}"
rm -rf "${DMG_STAGE}"
xcrun notarytool submit "${DMG_PATH}" --keychain-profile "${NOTARY_PROFILE}" --wait
xcrun stapler staple "${DMG_PATH}"
xcrun stapler validate "${DMG_PATH}"

APPCAST_WORK="build/appcast-${VERSION}"
rm -rf "${APPCAST_WORK}"
mkdir -p "${APPCAST_WORK}"
cp "${ZIP_PATH}" "${APPCAST_WORK}/${ARCHIVE_BASENAME}.zip"
cp CHANGELOG.md "${APPCAST_WORK}/${ARCHIVE_BASENAME}.md"
cp appcast.xml "${APPCAST_WORK}/appcast.xml"
"${GENERATE_APPCAST}" \
  --account iproteinstudio \
  --download-url-prefix "https://github.com/t-j-fryer/iProteinStudio/releases/download/${TAG}/" \
  --embed-release-notes \
  -o "${APPCAST_WORK}/appcast.xml" \
  "${APPCAST_WORK}"
cp "${APPCAST_WORK}/appcast.xml" "${DIST_DIR}/appcast.xml"
rm -rf "${APPCAST_WORK}"

echo "Release artifacts are ready in ${DIST_DIR}"
echo "The appcast contains a Sparkle EdDSA signature; do not edit it by hand."
[[ "${MODE}" == "--build" ]] && exit 0

command -v gh >/dev/null || fail "GitHub CLI is required for --publish."
gh auth status >/dev/null || fail "GitHub CLI is not authenticated."
git rev-parse "${TAG}" >/dev/null 2>&1 || git tag -a "${TAG}" -m "iProteinStudio ${VERSION}"
git push origin "${TAG}"
if gh release view "${TAG}" >/dev/null 2>&1; then
  gh release upload "${TAG}" "${ZIP_PATH}" "${DMG_PATH}" --clobber
else
  gh release create "${TAG}" "${ZIP_PATH}" "${DMG_PATH}" \
    --title "iProteinStudio ${VERSION}" --notes-file CHANGELOG.md
fi
cp "${DIST_DIR}/appcast.xml" appcast.xml
if ! git diff --quiet -- appcast.xml; then
  git add appcast.xml
  git commit -m "Publish iProteinStudio ${VERSION} update feed"
fi
git push origin main
echo "Published ${TAG}; signed appcast is live on main."
