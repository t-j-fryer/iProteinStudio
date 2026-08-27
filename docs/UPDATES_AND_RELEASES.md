# Application and engine updates

iProteinStudio deliberately has two independent update systems.

## What users receive

**Application updates** replace `iProteinStudio.app`: the interface, bundled
pipeline scripts, examples and compatibility patches. Sparkle shows the release
notes before installation. Users can disable automatic checks or automatic app
downloads in **iProteinStudio → Settings → Updates**.

**Engine and checkpoint changes are never Sparkle updates.** They remain in the
managed runtime under `~/.iproteinstudio`, are shown in **Engines** with their
purpose and approximate installed footprint, and require an explicit final
confirmation. Updating the app never removes or silently replaces projects,
results, MSAs, environments or weights.

Copies older than 0.2.0 contain no updater. Their users must install the first
signed 0.2.x DMG manually into `/Applications`; later signed releases can update
themselves.

## Trust boundary

- Sparkle is pinned exactly in `Package.swift`.
- Update archives are signed with the EdDSA key whose public half is in
  `release/sparkle_public_key.txt`; the private half lives only in the release
  maintainer's login Keychain.
- Distribution builds must be signed with an Apple Developer ID Application
  certificate, use Hardened Runtime, be notarized and have their ticket stapled.
- The feed uses HTTPS and Sparkle verifies an update before extraction.
- Model downloads retain the existing pinned URL, size and SHA-256 checks in
  `setup_pipeline.sh` and are outside Sparkle.

Back up the Sparkle private key to encrypted offline storage using the pinned
`generate_keys --account iproteinstudio -x` tool. Never place that exported file
in this repository or a cloud-synced working directory.

## One-time Apple setup

1. Join the Apple Developer Program and install a **Developer ID Application**
   certificate in the login Keychain. Apple documents the exact account-holder
   workflow at <https://developer.apple.com/help/account/certificates/create-developer-id-certificates/>.
2. Store notarization credentials without putting secrets in a shell script:

   ```bash
   xcrun notarytool store-credentials iproteinstudio-notary \
     --apple-id YOUR_APPLE_ID --team-id YOUR_TEAM_ID
   ```

3. Export the two non-secret selectors used by the release script:

   ```bash
   export IPROTEINSTUDIO_SIGNING_IDENTITY='Developer ID Application: NAME (TEAMID)'
   export IPROTEINSTUDIO_NOTARY_PROFILE='iproteinstudio-notary'
   ```

## Release procedure

1. Update `VERSION`, increment `BUILD_NUMBER`, and write concise user-facing
   changes in `CHANGELOG.md`. Explicitly say whether the release merely adds an
   optional engine choice; never imply the checkpoint is included in the app.
2. Commit and run:

   ```bash
   swift package resolve
   release/release_app.sh --preflight
   release/release_app.sh --build
   ```

3. Test the notarized DMG on another Apple-Silicon Mac, including update from the
   previous signed version and refusal/cancellation of any offered engine install.
4. Publish only after that acceptance test:

   ```bash
   release/release_app.sh --publish
   ```

`--publish` creates the Git tag and GitHub Release, uploads the notarized DMG and
Sparkle ZIP, then commits the generated signed `appcast.xml`. The generated feed
must not be edited after signing.

Sparkle's upstream security and publishing instructions remain authoritative:
<https://sparkle-project.org/documentation/> and
<https://sparkle-project.org/documentation/publishing/>.

The current custom release builder uses deep bundle signing because the app is a
SwiftPM executable assembled without an Xcode project. Before the first public
release, verify every nested Sparkle helper with `codesign --verify --deep
--strict`; moving to an Xcode archive is preferable if Apple's release tooling
reports any nested-code issue.
