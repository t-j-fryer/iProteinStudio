---
entry: 0034
title: Organize the app around workspaces and a first-class library
date: 2026-08-22
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, navigation, predict, projects, persistence, accessibility]
---

## Context

The sidebar still said **Design Projects** even though each saved container now
owns iterative design, RFdiffusion3 and ordinary prediction settings. A scientist
folding an unrelated batch of proteins had to create something called a design
project, then find Predict inside it. The predictions library was a secondary
button at the bottom of the sidebar, and workspace rename existed only in a
context menu. This followed the product audit in
[[0033-end-to-end-application-audit]].

## What was done

- Kept the internal `Project` type, configuration schema and `projects/` output
  directory for backward compatibility, but changed the product vocabulary to
  **Workspace**. A workspace can contain any combination of all three workflows.
- Added a persisted `preferredMode` with resilient decoding. Old saved projects
  default to Iterative design; switching workflow remembers what that workspace
  should reopen to.
- Added a first-class **Library** section for Predictions and All Runs, with
  visible counts. The old Predictions Library sheet remains the same durable data
  source rather than a second index.
- Made **New Prediction** the primary sidebar action. It immediately creates a
  uniquely named prediction workspace and opens Predict. **New Workspace** remains
  available for mixed or target-centred work. The File menu exposes both actions.
- Added visible ellipsis actions to workspace and cached-prediction rows, double-
  click rename, a rename pencil beside the active workspace name, reusable naming
  sheets, and destructive confirmation before deleting a workspace or cached
  prediction.
- Added deterministic, case-insensitive unique names and unique output slugs.
  Existing slugs never change when a display name is edited, preserving every
  saved result path and resumable manifest. Existing on-disk directory names are
  included when allocating a new slug, not just currently decoded workspaces.
- Replaced remaining user-facing “project” copy in engine removal, RFdiffusion3
  status, setup detail and accessibility labels. Internal identifiers remain to
  avoid a risky schema/path migration.
- Added `Tests/test_workspace_organization.sh` and its focused Swift harness for
  workflow persistence, unique names, unique slugs and required navigation/
  rename affordances.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Workspace naming/navigation contract | 1 suite | passing suites | 1/1 |
| Existing deterministic pipeline and Swift contracts | 8 suites | passing suites | 8/8 |
| Complete debug Swift build | 1 build | result | pass in 28.93 s |
| Release app-bundle build and ad-hoc signature | 1 build | result | pass in 43.20 s |
| Existing pre-change config | 2 workspaces | decoded and displayed | 2/2 |
| Existing prediction/run library | 13 + 13 records | visible after migration | 26/26 |
| Minimum supported window | 1080 × 772 px | clipped navigation/actions | none observed |

The minimum-window capture showed Library counts, both existing workspaces, their
mixed-workflow summaries, the active workspace title and pencil, all three
workflow tabs, Runs, both creation actions and the fixed Start action together.
No project directory was renamed or copied during migration.

The machine's active Command Line Tools install temporarily paired a Swift 6.3.3
compiler with a macOS 26.5 SDK built by Swift 6.3.2. The same source compiled with
the installed macOS 15.4 SDK. This is a local toolchain packaging mismatch, not an
application source error; the chosen SDK still exceeds the app's macOS 14 target.

## Decision and rationale

The app now uses **workspace** for the reusable context and **run** for one
execution. Predictions and runs are library objects. This matches what the app
actually stores without forcing users to decide a permanent project type before
they know what they will do.

We did not rename the Swift `Project` type or the on-disk `projects/` directory.
That would add migration risk without improving the interface. Likewise, freeform
prediction still uses the same durable workspace machinery rather than an
ephemeral special case: its inputs, outputs, cached MSA policy and history remain
reproducible and resumable.

The prediction library remains a focused sheet rather than becoming a second
`NavigationSplitView` detail route in this pass. Making it first-class in the
sidebar fixes discovery while avoiding competing selection models.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swiftpm-cache \
  ./Tests/test_workspace_organization.sh

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swiftpm-cache \
  swift build --disable-sandbox

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  ./build_app.sh release

codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
```

## Limits and what was not tested

- Assistive-control permission was unavailable to the automation process, so the
  release window was captured directly by CoreGraphics rather than driven by a
  full click/keyboard UI test. The views and action closures compiled, but this
  pass did not automate every menu, rename sheet and confirmation dialog.
- Existing state was decoded and displayed, but no destructive operation was
  exercised on the user's real workspaces or predictions.
- No GPU job was launched. This change does not alter a scientific command,
  predictor, MSA policy or run controller; those paths retain the acceptance
  evidence in [[0033-end-to-end-application-audit]].
- VoiceOver reading order and full keyboard traversal remain part of the standing
  accessibility gap.

## Next

Use the new layout during ordinary prediction and design work, then decide whether
Library should become a persistent detail destination rather than a sheet. Add a
UI automation target once the development runner has Accessibility permission,
covering New Prediction, workflow memory, workspace rename and cached-prediction
rename end to end.
