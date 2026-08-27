---
entry: 0044
title: Separate signed app updates from explicit checkpoint downloads
date: 2026-08-27
author: GPT-5.6
type: implementation
status: complete-with-external-release-blocker
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [updates, sparkle, signing, notarization, installer, usability, security]
---

## Context

An app copied to a Mac previously had no connection to later Git commits. On
launch it refreshed the managed pipeline from its own bundle, which meant an old
app repeatedly re-staged old scripts. Engine selection was separate from the app,
but pressing Setup or Install could begin a multi-gigabyte transfer without one
last summary of exactly what had been selected. Multiple old app copies could
also remain discoverable and be launched accidentally.

The product needs two deliberately different update contracts: small application
updates may be checked/downloaded automatically at the user's choice, whereas
scientific environments and checkpoints must never be implicit consequences of
updating the interface.

## What was done

### Application updates

- Pinned Sparkle 2.9.2 exactly at source revision
  `6276ba2b404829d139c45ff98427cf90e2efc59b` rather than following a moving
  package range.
- Added **Check for Updates…** to the application menu and an Updates settings
  window with separate opt-ins for automatic checks and automatic app downloads.
  Sparkle owns those UserDefaults; Studio does not maintain a conflicting copy.
- Added `VERSION` and `BUILD_NUMBER`; the app is now 0.2.0 (2) rather than a
  hard-coded 0.1.0 (1). The appcast uses the immutable bundle build number for
  ordering.
- Embedded the full Sparkle framework and helper services under
  `Contents/Frameworks`, added the required executable runpath, and put the HTTPS
  feed, public EdDSA key, release-note and verify-before-extraction settings in
  the generated Info.plist.
- Generated a dedicated EdDSA key under Keychain account `iproteinstudio`. Only
  public key `YYhs3f2PBFpgWsaFU7t04YzVPb9XjwfD5XVuEfA70Dw=` is versioned; the
  private key remains in the login Keychain and must be backed up offline.
- Added a user-facing changelog and an initially empty appcast. A disposable
  local archive generated a one-item appcast with a real EdDSA signature and the
  correct Sparkle build version.

### Engine and checkpoint consent

- Settings states unambiguously that app updates contain the interface and
  bundled pipeline only. They never download, replace or remove an engine,
  checkpoint, project, result or alignment.
- First-run setup and later Engines management now stop at a shared review sheet
  before downloading. It lists each component, approximate installed footprint,
  purpose, checkpoint note and automatically added dependency. **Cancel** changes
  nothing; only **Install now** hands the reviewed set to the installer.
- Existing resumable transfer, pinned URL/size/SHA-256 validation and removable
  managed-component behavior are unchanged. No checkpoint was downloaded during
  this work.

### Canonical installation and duplicate copies

- A signed distribution build launched outside `/Applications` or the user's
  Applications folder asks the user to reveal and move that exact copy. Local
  development builds do not show the prompt.
- Updates settings can ask Spotlight for every app with the retained bundle ID,
  show the current and other versions/paths, reveal them in Finder, and—with a
  second destructive confirmation—move only a revalidated non-current `.app` to
  the Bin. The guard reopens the candidate bundle and rechecks the bundle ID;
  `~/.iproteinstudio` is never a removal target.
- The Engines shortcut moved from Command-comma, which belongs to macOS Settings,
  to Command-Shift-E.

### Release pipeline

`release/release_app.sh` now has three explicit stages:

1. `--preflight` matches the named Keychain EdDSA key, Developer ID Application
   identity and notarytool Keychain profile.
2. `--build` requires a clean tracked tree, builds with Hardened Runtime,
   Developer-ID signs, verifies, notarizes/staples the app, creates a DMG with an
   Applications link, notarizes/staples that DMG, and generates a signed Sparkle
   appcast from the ZIP alone.
3. `--publish` creates the version tag and GitHub release, uploads the notarized
   DMG/ZIP and commits the generated appcast to the stable HTTPS feed.

Secrets are neither command-line values nor repository files: the private
Sparkle key and Apple notarization credential are Keychain items. Documentation
in `docs/UPDATES_AND_RELEASES.md` covers the one-time Apple setup, release steps,
key backup and second-Mac acceptance requirement.

## Results

| Check | Result |
|---|---|
| Debug Swift build with pinned Sparkle binary artifact | pass |
| Release app assembly, embedded framework and all nested ad-hoc signatures | pass |
| Mach-O dependency | `@rpath/Sparkle.framework/Versions/B/Sparkle` 2.9.2 |
| Bundle runpath | `@executable_path/../Frameworks` present |
| Bundle version/feed/public-key metadata | 0.2.0 (2), HTTPS feed, dedicated public key |
| Disposable signed appcast | one update, EdDSA signature present, build version 2 |
| Live application launch after packaging | pass; remained running |
| Live menu inspection | Check for Updates and Settings present |
| Live Settings visual inspection | controls fit at 620×620; app/model boundary visible |
| Live Engines visual inspection | update boundary and installed footprints visible |
| Release preflight without Apple identity | stopped with exit 3 before build/publish |
| All four checked-in shell suites | pass |
| Deterministic Python contracts under managed RDKit runtime | pass |
| Optional live generic-ligand RCSB acceptance | pass for caffeine, aspirin, (S)-ibuprofen, beta-D-glucose and acetate |

The first assembled Sparkle build initially failed at launch even though
compilation and deep signature verification passed. `dyld` could not resolve
`@rpath/Sparkle.framework/Versions/B/Sparkle` because the hand-built executable
lacked the standard `@executable_path/../Frameworks` runpath. That failure was
reproduced directly (exit 134), corrected in `Package.swift`, and the rebuilt app
then launched. This is why signing and syntax checks are not substitutes for a
real bundle launch.

The disposable appcast test exposed a second release-only defect before commit:
Sparkle resolves `-o appcast.xml` against the caller's working directory rather
than the archive directory. The test therefore temporarily replaced the empty
repository feed with an entry for a nonexistent local-test ZIP. The public feed
was restored, the release script now passes the explicit appcast-work path, and
a source contract prevents that regression. No invalid feed was committed or
published.

The generic system Python lacked RDKit and therefore could not import the
optional live-ligand test. The suite was rerun through Studio's installed,
managed Boltz interpreter—the same dependency-bearing runtime expected by these
chemistry helpers—and both the deterministic chemistry contracts and live RCSB
acceptance passed. No package was silently installed into the system Python.

## Decision and rationale

Application updates and scientific model downloads are separate trust and cost
domains. Users may opt into automatic delivery of a relatively small, signed app
without ever consenting to a new multi-gigabyte model. New capabilities can be
explained in release notes, but their engines remain visibly optional in the
Engine manager. This also preserves scientific reproducibility: a GUI update
cannot silently change a checkpoint behind an existing campaign.

The legacy bundle identifier `ai.nanohunter.studio` is retained. Changing it now
would create another independent application identity, lose updater preferences
and make duplicate-copy cleanup less reliable.

## Reproduce

```bash
cd /path/to/iProteinStudio
swift package resolve
caffeinate -dimsu swift build
caffeinate -dimsu ./build_app.sh release
bash Tests/test_update_release_contract.sh
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
otool -L build/iProteinStudio.app/Contents/MacOS/iProteinStudio
otool -l build/iProteinStudio.app/Contents/MacOS/iProteinStudio
release/release_app.sh --preflight
```

## Limits and what was not tested

- There is no Developer ID identity on this Mac. No distribution signature,
  notarization request, staple, DMG acceptance or GitHub Release was produced.
- No old signed build exists, so a genuine old-to-new Sparkle installation,
  relaunch, delta update, interrupted update or key-rotation path was tested.
- The first signed updater-capable release still requires a manual DMG install
  for every existing user. Only releases after that can arrive automatically.
- The live engine sheet was inspected on a machine where every component was
  already installed; the no-download confirmation path is compilation- and
  source-contract tested but was not allowed to reinstall a large component
  merely to create a screenshot.
- Duplicate-copy discovery was not used to remove anything during acceptance.
- No GPU prediction/design work or model download was necessary or performed.

## Next

Obtain/install the Apple Developer ID Application certificate and configure a
notarytool Keychain profile. Then build the first signed DMG, install it manually
on a second Apple-Silicon Mac, and test 0.2.0 → a higher-build signed stub through
Sparkle before `--publish`. Preserve the notarization logs, appcast, archive
hashes and screenshots as release evidence.
