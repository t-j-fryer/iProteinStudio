#!/usr/bin/env bash
# Build iProteinStudio and assemble a double-clickable .app bundle.
#
# Works with just the Command Line Tools (no full Xcode needed). For a
# distributable, notarized app, open Package.swift in Xcode and archive with a
# Developer ID — this script produces an ad-hoc-signed .app for local use.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
CONFIG="${1:-release}"
APP_NAME="iProteinStudio"
BIN_NAME="iProteinStudio"
BUNDLE_ID="ai.nanohunter.studio"
APP_VERSION="${IPROTEINSTUDIO_VERSION:-$(tr -d '[:space:]' < VERSION)}"
APP_BUILD="${IPROTEINSTUDIO_BUILD_NUMBER:-$(tr -d '[:space:]' < BUILD_NUMBER)}"
UPDATE_FEED_URL="${IPROTEINSTUDIO_UPDATE_FEED_URL:-https://raw.githubusercontent.com/t-j-fryer/iProteinStudio/main/appcast.xml}"
SPARKLE_PUBLIC_KEY="${IPROTEINSTUDIO_SPARKLE_PUBLIC_KEY:-$(tr -d '[:space:]' < release/sparkle_public_key.txt)}"
SIGNING_IDENTITY="${IPROTEINSTUDIO_SIGNING_IDENTITY:--}"
UNSIGNED_BETA="${IPROTEINSTUDIO_UNSIGNED_BETA:-0}"
[[ "${UNSIGNED_BETA}" == "0" || "${UNSIGNED_BETA}" == "1" ]] \
  || { echo "IPROTEINSTUDIO_UNSIGNED_BETA must be 0 or 1." >&2; exit 2; }
if [[ "${SIGNING_IDENTITY}" == "-" ]]; then
  if [[ "${UNSIGNED_BETA}" == "1" ]]; then
    DISTRIBUTION_BUILD=true
    SPARKLE_UPDATE_BUILD=true
    DISTRIBUTION_CHANNEL="unsigned-beta"
  else
    DISTRIBUTION_BUILD=false
    SPARKLE_UPDATE_BUILD=false
    DISTRIBUTION_CHANNEL="development"
  fi
else
  [[ "${UNSIGNED_BETA}" == "0" ]] \
    || { echo "An unsigned beta cannot also use a Developer ID identity." >&2; exit 2; }
  DISTRIBUTION_BUILD=true
  SPARKLE_UPDATE_BUILD=true
  DISTRIBUTION_CHANNEL="developer-id"
fi

[[ "${APP_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9]+)*$ ]] \
  || { echo "Invalid VERSION: ${APP_VERSION}" >&2; exit 2; }
[[ "${APP_BUILD}" =~ ^[1-9][0-9]*$ ]] \
  || { echo "Invalid BUILD_NUMBER: ${APP_BUILD}" >&2; exit 2; }
[[ "${UPDATE_FEED_URL}" == https://* ]] \
  || { echo "Update feed must use HTTPS." >&2; exit 2; }
[[ ${#SPARKLE_PUBLIC_KEY} -ge 40 ]] \
  || { echo "Sparkle public key is absent or malformed." >&2; exit 2; }

echo "==> swift build -c ${CONFIG}"
swift build -c "${CONFIG}"

BIN_DIR="$(swift build -c "${CONFIG}" --show-bin-path)"
APP="build/${APP_NAME}.app"
rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources" "${APP}/Contents/Frameworks"

echo "==> assembling ${APP}"
cp "${BIN_DIR}/${BIN_NAME}" "${APP}/Contents/MacOS/${BIN_NAME}"

# Package resources explicitly. SwiftPM's executable-target Bundle.module
# accessor embeds an absolute .build path in the executable and assumes the
# resource bundle lives at the sealed .app root. Neither is suitable for a
# reproducible hand-assembled macOS bundle.
RESOURCE_SOURCE="Sources/iProteinStudio/Resources"
RESOURCE_DIRECTORY="iProteinStudioResources"
[[ -f "${RESOURCE_SOURCE}/pipeline/PIPELINE_VERSION" ]] \
  || { echo "Source resource directory is incomplete: ${RESOURCE_SOURCE}" >&2; exit 2; }
/usr/bin/ditto "${RESOURCE_SOURCE}" "${APP}/Contents/Resources/${RESOURCE_DIRECTORY}"
[[ -f "${APP}/Contents/Resources/${RESOURCE_DIRECTORY}/pipeline/PIPELINE_VERSION" ]] \
  || { echo "Packaged resource directory is incomplete." >&2; exit 2; }

# SwiftPM resource copying does not consult .gitignore. Remove generated Python
# and Numba caches from the assembled copy so a developer's local run can never
# inflate or contaminate a release bundle.
find "${APP}" -type d \
  \( -name __pycache__ -o -name numba_cache \) -prune -exec rm -rf -- {} +
find "${APP}" -type f \
  \( -name '*.pyc' -o -name '.DS_Store' \) -delete
if find "${APP}" \
    \( -type d \( -name __pycache__ -o -name numba_cache \) \
       -o -type f -name '*.pyc' \) -print -quit | grep -q .; then
  echo "Generated cache artifacts remain in the app bundle." >&2
  exit 2
fi

# SwiftPM links Sparkle dynamically. A hand-assembled bundle must embed the
# framework (including its updater helpers and symlinks) just as Xcode's
# "Embed & Sign" phase would.
SPARKLE_FRAMEWORK=".build/artifacts/sparkle/Sparkle/Sparkle.xcframework/macos-arm64_x86_64/Sparkle.framework"
[[ -d "${SPARKLE_FRAMEWORK}" ]] \
  || { echo "Sparkle framework is missing; run swift package resolve." >&2; exit 2; }
SPARKLE_LICENSE=".build/checkouts/Sparkle/LICENSE"
[[ -f "${SPARKLE_LICENSE}" ]] \
  || { echo "Sparkle license is missing; run swift package resolve." >&2; exit 2; }
/usr/bin/ditto "${SPARKLE_FRAMEWORK}" "${APP}/Contents/Frameworks/Sparkle.framework"

# Binary distributions must carry the notices for code embedded in the app,
# not merely link to a mutable web page. Keep the exact upstream texts beside
# the human-readable inventory.
mkdir -p "${APP}/Contents/Resources/ThirdPartyLicenses"
cp THIRD_PARTY_NOTICES.md "${APP}/Contents/Resources/ThirdPartyLicenses/README.md"
cp third_party_licenses/RDKit-LICENSE.txt \
  "${APP}/Contents/Resources/ThirdPartyLicenses/RDKit-LICENSE.txt"
cp third_party_licenses/3Dmol-LICENSE.txt \
  "${APP}/Contents/Resources/ThirdPartyLicenses/3Dmol-LICENSE.txt"
cp Sources/iProteinStudio/Resources/web/py2dmol/LICENSE \
  "${APP}/Contents/Resources/ThirdPartyLicenses/py2Dmol-LICENSE.txt"
cp Sources/iProteinStudio/Resources/pipeline/THIRD_PARTY_NOTICES.md \
  "${APP}/Contents/Resources/ThirdPartyLicenses/IPSAE-LICENSE.md"
cp "${SPARKLE_LICENSE}" \
  "${APP}/Contents/Resources/ThirdPartyLicenses/Sparkle-LICENSE.txt"

cat > "${APP}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key><string>${APP_NAME}</string>
  <key>CFBundleExecutable</key><string>${BIN_NAME}</string>
  <key>CFBundleIdentifier</key><string>${BUNDLE_ID}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${APP_VERSION}</string>
  <key>CFBundleVersion</key><string>${APP_BUILD}</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSHumanReadableCopyright</key><string>iProteinStudio</string>
  <key>SUFeedURL</key><string>${UPDATE_FEED_URL}</string>
  <key>SUPublicEDKey</key><string>${SPARKLE_PUBLIC_KEY}</string>
  <key>SUShowReleaseNotes</key><true/>
  <key>SUVerifyUpdateBeforeExtraction</key><true/>
  <key>IPStudioDistributionBuild</key><${DISTRIBUTION_BUILD}/>
  <key>IPStudioSparkleUpdateBuild</key><${SPARKLE_UPDATE_BUILD}/>
  <key>IPStudioDistributionChannel</key><string>${DISTRIBUTION_CHANNEL}</string>
</dict>
</plist>
PLIST

# Local builds remain ad-hoc signed. Distribution builds pass a Developer ID
# identity and gain Hardened Runtime + timestamping before notarization.
if [[ "${SIGNING_IDENTITY}" == "-" ]]; then
  codesign --force --deep --sign - "${APP}"
  if [[ "${UNSIGNED_BETA}" == "1" ]]; then
    echo "   ad-hoc signed trusted beta (Sparkle updates require an EdDSA-signed archive)"
  else
    echo "   ad-hoc signed development build (self-update disabled)"
  fi
else
  codesign --force --deep --options runtime --timestamp \
    --sign "${SIGNING_IDENTITY}" "${APP}"
  echo "   signed with ${SIGNING_IDENTITY}"
fi
codesign --verify --deep --strict --verbose=2 "${APP}"

echo "✅ Built ${APP}"
echo "   Version: ${APP_VERSION} (${APP_BUILD})"
echo "   Launch with:  open \"${APP}\""
