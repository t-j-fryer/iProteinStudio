---
entry: 0023
title: Fit viewer controls and audit the minimum-window GUI
date: 2026-08-18
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, viewer, rfd3, accessibility]
---

## Context

After py2Dmol became the shared structure renderer in
[[0022-share-msas-and-adopt-py2dmol]], its control rail was visibly clipped in
Target Prep. The structure canvas occupied its nominal upstream width and the rail
continued underneath the native hotspot sidebar. A second GUI pass was requested,
including other workflows and constrained window sizes.

## What was done

The cause was not the SwiftUI `HStack`: py2Dmol writes its configured 600 by 600
starting size as inline styles during initialisation. Those inline widths outranked
Studio's responsive stylesheet, so the canvas would not surrender space to the
190-point control rail.

The Studio host stylesheet now deliberately outranks only those upstream inline
starting dimensions. The viewer wrapper can shrink, the canvas container takes the
remaining flex width and height, and the root uses a border-box model so padding does
not add eight points beyond every edge. Compact thumbnail mode also has zero minimum
dimensions so small tiles do not overflow. py2Dmol's `ResizeObserver` remains in
charge of resizing the backing canvas and rerendering at the resulting dimensions.

The object chooser is hidden after Studio loads a structure. Studio presents one
named object per viewer, so the chooser had no useful choice and became an unreadable
row in Target Prep. Style, Save, Rotate, all style controls, and the rail's vertical
scrolling remain available.

The pass also found a separate UI truthfulness bug. Target Prep's removable hotspot
chips always said chain `B`; RFdiffusion3 adopts the monomer predicted there as chain
`A`. The chain label is now a workflow parameter: iterative templates show `B`, and
RFdiffusion3 target preparation shows `A`.

## Results

No performance measurements were made. A real WKWebView geometry harness loaded the
bundled PDB and expanded Style at every actual presentation size:

| Presentation | Viewport | Result |
|---|---:|---|
| Target Prep viewer area | 650 × 580 pt | pass; canvas ends before rail; rail ends inside root |
| minimum completed-run detail | 620 × 460 pt | pass; no overlap or horizontal overflow |
| dashboard structure inspector | 720 × 460 pt | pass; no overlap or horizontal overflow |
| compact thumbnail | 180 × 130 pt | pass; canvas exactly fits; controls hidden |

The rebuilt application was then exercised through macOS Accessibility and real screen
captures. At the app's declared minimum 1080 by 720 point window:

- Target Prep displayed its header, full collapsed py2Dmol rail, native hotspot sidebar,
  footer, and predicted structure without clipping.
- RFdiffusion3 retained its workflow navigation, independent form scrollbar, validation
  bar, and Start control.
- Predict retained its navigation, form scrollbar, parsed-fold summary, and Start control.
- Iterative Design retained its navigation, form scrollbar, and Start control.

The iterative CLI, RFdiffusion3/Predict helper, and native request contract suites pass.
Debug and release builds pass, and the release bundle's signature verifies.

## Decision and rationale

Studio owns responsive layout while upstream owns rendering. Overriding only the
initial inline size preserves py2Dmol's renderer and `ResizeObserver` behavior instead
of forking its canvas implementation. A wider sheet was rejected: it would hide the
underlying bug, fail again in the 620-point result detail, and consume unnecessary
screen space.

The one-object chooser was removed from this host because a disabled-looking control
with no alternate value makes the interface harder to understand. It can return if
Studio later presents multiple independently named objects in one viewer.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

# Real WebKit geometry test used during this entry.
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-layout-clang-cache \
SWIFT_MODULECACHE_PATH=/private/tmp/iproteinstudio-layout-swift-cache \
swiftc /private/tmp/Py2DmolLayoutHarness.swift -framework AppKit -framework WebKit \
  -o /private/tmp/iproteinstudio-layout-harness
caffeinate -dimsu /private/tmp/iproteinstudio-layout-harness

caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  Tests/test_workflow_pipelines.py

env CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-gui-clang-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-gui-swift-cache \
  caffeinate -dimsu swift build
caffeinate -dimsu ./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
```

For the real-app pass, launch the release build, set its window to 1080 by 720 points,
open each workflow, then open RFdiffusion3 Target Prep and choose the existing
IntelliFold prediction.

## Limits and what was not tested

- The visual pass used one display scale, light appearance, and macOS 26.x.
- Dark appearance, increased contrast, Reduce Motion, large accessibility text, and a
  complete VoiceOver/keyboard-only traversal were not tested.
- The Save panel's in-page construction and PNG data generation were tested in the
  preceding entry, but the native save/download destination was not exercised here.
- A complex with multiple models/frames and a large multi-chain complex were not part
  of this layout pass.
- The 3Dmol hydrophobic-surface mode was not changed or retested.

## Next

Make the real WebKit geometry matrix a checked-in XCTest or UI-test target, then add
dark-mode and keyboard-focus screenshots at the same four viewports.
