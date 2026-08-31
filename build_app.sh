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
if [[ "${SIGNING_IDENTITY}" == "-" ]]; then
  DISTRIBUTION_BUILD=false
else
  DISTRIBUTION_BUILD=true
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

# SwiftPM resource bundle (Bundle.module) -> app Resources so it resolves.
if [ -d "${BIN_DIR}/${BIN_NAME}_${BIN_NAME}.bundle" ]; then
  cp -R "${BIN_DIR}/${BIN_NAME}_${BIN_NAME}.bundle" "${APP}/Contents/Resources/"
fi

# SwiftPM resource copying does not consult .gitignore. Remove generated Python
# and Numba caches from the assembled copy so a developer's local run can never
# inflate or contaminate a release bundle.
find "${APP}/Contents/Resources" -type d \
  \( -name __pycache__ -o -name numba_cache \) -prune -exec rm -rf -- {} +
find "${APP}/Contents/Resources" -type f \
  \( -name '*.pyc' -o -name '.DS_Store' \) -delete
if find "${APP}/Contents/Resources" \
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
/usr/bin/ditto "${SPARKLE_FRAMEWORK}" "${APP}/Contents/Frameworks/Sparkle.framework"

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
</dict>
</plist>
PLIST

# Local builds remain ad-hoc signed. Distribution builds pass a Developer ID
# identity and gain Hardened Runtime + timestamping before notarization.
if [[ "${SIGNING_IDENTITY}" == "-" ]]; then
  codesign --force --deep --sign - "${APP}"
  echo "   ad-hoc signed (development only; self-update is not distributable)"
else
  codesign --force --deep --options runtime --timestamp \
    --sign "${SIGNING_IDENTITY}" "${APP}"
  echo "   signed with ${SIGNING_IDENTITY}"
fi
codesign --verify --deep --strict --verbose=2 "${APP}"

echo "✅ Built ${APP}"
echo "   Version: ${APP_VERSION} (${APP_BUILD})"
echo "   Launch with:  open \"${APP}\""
