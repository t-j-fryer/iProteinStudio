---
entry: 0268
title: Adopt the natural app identity and a short native introduction
date: 2026-10-02
author: Codex
type: implementation
status: complete
machine: local macOS host; native SwiftUI review
tags: [ui, branding, onboarding]
---

## Context

The user selected Terra Loop (icon 02 in [[0263-explore-natural-evolution-brand]])
and requested a native aesthetic matching the website from
[[0265-refresh-natural-launch-site]]. They requested the simple introduction
planned in [[0264-plan-native-onboarding]], explicitly deferring the My First
Protein Design lesson. Read the discussion in “Prototype Pipeline Builder
Features” and its local onboarding concept document before implementation.

## What was done

- Added adaptive paper, chalk, moss and clay surfaces in `StudioStyle.swift`,
  shared form cards and group boxes, workflow artwork headers, a branded
  sidebar and an illustrated empty workspace. Native action controls and
  scientific status colours retain their standard semantics.
- Added Appearance settings (Follow System by default, Light, Dark). Native
  controls retain automatic text contrast; increased-contrast card borders are
  supported. Art is static and decorative in the accessibility tree.
- Added a skippable three-page `StudioIntroductionView`: capabilities, four
  workflows, and the input-to-evidence process. Help and the workspace toolbar
  reopen it in a native window. It starts no jobs and downloads nothing.
- First-launch routing uses independently persisted introduction state and
  `IntroductionPolicy`. Existing work, installed engines, installation progress,
  and recovery take precedence. Completing orientation does not complete setup.
- Integrated Terra Loop as the Dock/Finder icon via `CFBundleIconFile`, plus
  seven bundled PNGs. Prepared the transparent Terra Loop derivative using
  built-in image_gen; copied other selected originals without editing.
  Exact edit prompts and provenance live in `Resources/Brand/PROVENANCE.txt`.
  `tools/export_app_icon.sh` creates the multi-resolution ICNS with sips/iconutil.
- Moved the Protein Hunter validation message onto its own run-bar row after
  native review found it squeezed to a narrow column next to the controls.

## Results

No measurements — UI implementation only.

- `swift build` passed after final changes.
- `swift test --filter IntroductionPolicyTests` passed: one exhaustive test
  covering all 32 boolean routing combinations.
- `bash build_app.sh debug` built the app; strict recursive code-signature
  verification passed. Verified ICNS header/length, bundled icon equality, and
  the Info.plist icon reference.
- Native UI review used a separately identified copy of the actual executable,
  with `IPROTEINSTUDIO_TEST_SUPPORT_ROOT` pointing into
  `build/appearance-review/isolated-runtime`. No real project data was used.
- Verified introduction Continue, Back, Return-key navigation, completion to
  setup, Help reopening, and Escape dismissal. The completed introduction stayed
  dismissed on relaunch. Verified workspace creation in that isolated runtime,
  artwork loading, the Protein Hunter form, the corrected compact run bar,
  and Light/Dark switching through Settings.
- Workspace routing in the fixture used a test-only receipt referencing
  `/usr/bin/false` and a text artifact. Scientific engine detection correctly
  showed engines unavailable and Start disabled; no fake weights were created.

## Decision and rationale

Keep rich imagery in orientation and workspace entry, and use smaller artwork
beside workflow titles. Routine controls remain familiar native controls. A
short optional introduction establishes vocabulary without adding a learning
mode, recipe builder, simulated design task, or mandatory checklist. Existing
setup/recovery remains authoritative rather than treating welcome completion
as installed capability.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
bash tools/export_app_icon.sh
swift build
swift test --filter IntroductionPolicyTests
bash build_app.sh debug
```

Open `build/iProteinStudio.app` and use Help → Discover iProteinStudio.
Use Settings → Appearance to inspect Light and Dark. For isolated testing,
copy the built app, assign a different bundle identifier, and launch its binary
with `IPROTEINSTUDIO_TEST_SUPPORT_ROOT` pointing to a disposable test directory.
Never put UI fixture receipts in the real managed runtime.

## Limits and what was not tested

No scientific GPU jobs, model downloads, predictor regressions, benchmarks,
release publication, notarization, or installed application replacement. No
full VoiceOver, localization, or older-macOS audit. All four form changes compile;
full native interaction coverage was limited to Protein Hunter. The native
computer-use connection closed while starting the NISE visual check, and one
reconnection attempt also failed, so that additional visual check is not claimed.
ImageGen preserves the selected concept rather than providing pixel-identical
background extraction. Tiny texture details are not optically tuned by size.
The new native introduction does not implement the deferred lesson or builder.

## Next

Review the local build with the user before a release. Follow up with a broader
accessibility and supported-macOS review, and refine individual small-size glyphs
if the chosen visual identity is adopted permanently.

## Delivery

Local build: `build/iProteinStudio.app`. No release version bumped or remote
publication performed. Existing unrelated MCP, manuscript, validation, and
prototype changes were preserved. No commit was made.
