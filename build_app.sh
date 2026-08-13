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

echo "==> swift build -c ${CONFIG}"
swift build -c "${CONFIG}"

BIN_DIR="$(swift build -c "${CONFIG}" --show-bin-path)"
APP="build/${APP_NAME}.app"
rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"

echo "==> assembling ${APP}"
cp "${BIN_DIR}/${BIN_NAME}" "${APP}/Contents/MacOS/${BIN_NAME}"

# SwiftPM resource bundle (Bundle.module) -> app Resources so it resolves.
if [ -d "${BIN_DIR}/${BIN_NAME}_${BIN_NAME}.bundle" ]; then
  cp -R "${BIN_DIR}/${BIN_NAME}_${BIN_NAME}.bundle" "${APP}/Contents/Resources/"
fi

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
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSHumanReadableCopyright</key><string>iProteinStudio</string>
</dict>
</plist>
PLIST

# Ad-hoc code signature so Gatekeeper lets you run it locally.
codesign --force --deep --sign - "${APP}" 2>/dev/null || \
  echo "   (codesign skipped; you can still run the app)"

echo "✅ Built ${APP}"
echo "   Launch with:  open \"${APP}\""
