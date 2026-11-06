---
entry: 0785
title: Fix molecule heading and add a resize grip
date: 2026-11-06
author: Codex
type: bugfix
status: in-progress
machine: Apple Silicon development Mac; native SwiftUI/WebKit checks
tags: [ui, ligand, viewer]
---

## Context

User reported the Molecule view label wrapping one syllable at a time and
requested a bottom-right grip to change both viewer dimensions. Also asked
whether the viewer uses existing tools. Follows Lab0784.

## What was done

Separate a single-line heading from the labelled-but-visually-hidden segmented
picker; compact 2D/3D buttons. Add a bottom-right diagonal resize grip with native
macOS resize cursor, bounded width/height and persisted per-app dimensions.
Double-click resets the size. Restrict gestures to the grip so molecule rotation,
pan, zoom and picking keep their existing input handling. The shared panel owns
its border; remove the fixed heights/borders at RFD3/RFD4, Protein Hunter and NISE
call sites. Width follows available form space; height is bounded240–1000points.

The engine remains existing RDKit (WASM2D and PythonETKDGv3 display conformer),
3Dmol.js WebGL rendering and WKWebView embedding. Studio's own code supplies
controls, atom-map/selection bridges, annotations and geometry overlays. No
renderer, chemistry method, model, runtime or scientific setting was replaced.

## Results

Swift build and signed beta0.2.35-dev/build85 pass. Native ethanol atom-picker
regression passes selections, condition highlights, resize redraw retention and
exact directed-bond picking after zoom/rotation/reset. No performance measurement
or scientific/model inference. Native screenshot reviewed: the heading remains on one line and the diagonal
grip is visible at the panel’s bottom right. Matching public0.2.35/build85 app
build passes. Actual drag/relaunch verification is pending permission to restart
the running beta; build84 remains installed/running.

## Decision and rationale

A separate heading avoids SwiftUI squeezing the picker label. Shared sizing
removes contradictory fixed parent heights and keeps a single interaction in
all molecule forms. Dimensions persist in each app's own preferences; reset
returns to full available width and320points height.

## Reproduce

```bash
CLANG_MODULE_CACHE_PATH=/tmp/studio-geometry-clang-cache SWIFT_MODULECACHE_PATH=/tmp/studio-geometry-swift-cache bash release/build_local_beta.sh
bash Tests/test_ligand_atom_selection.sh
```

## Limits and what was not tested

No fresh GPU run, general ligand-size benchmark or older-Mac hardware test.
macOS14 uses a crosshair cursor; macOS15+ uses the native diagonal resize cursor.
Public changes remain a local candidate until explicit publication.

## Next

Install/reopen build85 after permission to close the current beta, then verify
actual dragging. Automatic approval review rejected quitting the beta because
it could discard unsaved workspace state; user permission requested.
