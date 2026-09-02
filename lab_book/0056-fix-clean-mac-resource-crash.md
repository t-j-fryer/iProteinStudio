---
entry: 0056
title: Fix the clean-Mac packaged-resource startup crash
date: 2026-09-01
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, macOS
tags: [release, resources, swiftpm, crash, reproducibility, distribution]
---

# Fix the clean-Mac packaged-resource startup crash

## Failure

The first external installation of unsigned beta `0.2.0 (2)` crashed immediately
on macOS 14.6.1 with `EXC_BREAKPOINT`. The top frames were:

```text
_assertionFailure
closure #1 in variable initialization expression of static NSBundle.module
AppState.init()
```

This was an application packaging defect, not Gatekeeper, ad-hoc signing or
Sparkle.

## Root cause

SwiftPM generated an executable-target `Bundle.module` accessor that searched:

1. `Bundle.main.bundleURL/iProteinStudio_iProteinStudio.bundle`; then
2. an absolute path under the developer checkout's `.build` directory.

For a macOS application, the first location is the sealed `.app` root, where the
hand-built packager cannot legally place arbitrary resources. The packager used
the conventional `Contents/Resources` location, which the generated accessor did
not inspect. Local launches succeeded only because option 2 existed on the build
Mac. A new Mac had no such path and the generated accessor called `fatalError`.

The initial direct attempt to place the generated bundle at the app root was
correctly rejected by `codesign` as unsealed root contents. The solution therefore
had to remove the incompatible accessor rather than weaken bundle signing.

## Fix

- Removed SwiftPM executable-resource generation from `Package.swift` and
  explicitly excluded the source resource directory from compilation.
- `build_app.sh` now copies `Sources/iProteinStudio/Resources` to the standard
  `Contents/Resources/iProteinStudioResources` directory and validates its
  pipeline sentinel before signing.
- `AppPaths` resolves packaged resources from `Bundle.main.resourceURL`.
- Development builds resolve resources from an explicit environment override,
  the current checkout or directories derived relative to the executable; no
  machine-specific source path is embedded.
- Added package-layout and clean-machine launch regression tests.
- The release script runs the package-layout contract before producing either a
  trusted beta or Developer ID artifact.
- Incremented `BUILD_NUMBER` from 2 to 3 so the corrected app is distinguishable
  from the crashing artifact.

## Verification

| Check | Result |
|---|---|
| `swift build` | Passed without unhandled-resource warnings |
| Swift release build | Passed |
| macOS deep strict code-signature check | Passed |
| Packaged resource contract | Passed |
| Absolute checkout path search in packaged executable | No match |
| Launch from `/tmp`, outside source checkout | Remained running for 5 s |
| Read-only DMG launch from `/tmp` | Remained running for 5 s |
| DMG resource sentinel and build number 3 | Present/correct |
| Unsigned-beta release contract | Passed |
| Existing signed-release contract | Passed |
| Iterative-results UI contract | Passed |
| DMG and ZIP SHA-256 manifests | Passed |
| Sparkle ZIP EdDSA verification | Passed |

Corrected private-test artifact checksums:

- DMG: `2a1bbd23b640f7a543e00a320baf1978a128517c856504687cf8610cd0edb597`
- ZIP: `0a6c5db55bf625fc7f5aba0ada550f3945364ad871187176c4df723a7fa64c93`

These supersede the build 2 artifacts and hashes in Entries 0054 and 0055.

## What was not tested

- Build 3 has not yet been opened on the reporting Mac after transfer through a
  browser or cloud-download route.
- A new-user engine installation and scientific run were not repeated; the
  change is confined to how already-versioned bundled resources are located.
- A real hosted beta-to-beta Sparkle update remains pending two clean published
  builds with increasing build numbers.
- The artifact remains labelled `dirty-local-test`; it must not become the
  public beta without committing and rebuilding from a clean tree.

## Acceptance

Delete the previously copied build 2 application, install build 3 from the new
DMG, complete the one-time macOS **Open Anyway** flow and confirm that the main
window opens. Then install the core component and run one small bundled example
to exercise resource staging on the second Mac.
