#!/usr/bin/env bash
# Build, sign, notarize and optionally publish a Sparkle-compatible release.
# The Sparkle private key stays in the login Keychain; Apple credentials stay
# in a notarytool Keychain profile. Neither secret is accepted as a file here.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

MODE="${1:---preflight}"
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

[[ "${MODE}" == "--preflight" || "${MODE}" == "--build" || "${MODE}" == "--publish" ]] \
  || fail "Usage: release/release_app.sh [--preflight|--build|--publish]"
[[ "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9]+)*$ ]] \
  || fail "VERSION is malformed: ${VERSION}"
[[ "${BUILD_NUMBER}" =~ ^[1-9][0-9]*$ ]] || fail "BUILD_NUMBER must be a positive integer."
[[ -x "${GENERATE_KEYS}" && -x "${GENERATE_APPCAST}" ]] \
  || fail "Sparkle tools are absent. Run: swift package resolve"
[[ -n "${PUBLIC_KEY}" ]] || fail "The checked-in Sparkle public key is empty."

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
security find-identity -v -p codesigning | grep -Fq "${SIGNING_IDENTITY}" \
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
