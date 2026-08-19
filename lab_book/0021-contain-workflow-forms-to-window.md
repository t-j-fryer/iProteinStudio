---
entry: 0021
title: Keep long workflow forms inside the window
date: 2026-08-17
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, ui, navigation, macos]
---

## Context

Opening the RFdiffusion3 workflow could make the detail column adopt the form's full
ideal height. The top workflow picker then moved above the visible window and the form
did not behave as a bounded scrolling region, leaving the user unable to switch tabs.
This follows the persistent-navigation decision in
[[0014-runtime-promotion-and-persistent-navigation]].

## What was done

`ProjectDetailView` now measures the real detail viewport with `GeometryReader` and
constrains its fixed workflow header and selected workflow content to that viewport.
The content gets the remaining finite height and is clipped at that boundary, so a
workflow's own `ScrollView` scrolls instead of enlarging the split-view detail.

`RFD3View` is also explicitly constrained to the available height. Its workflow form
remains the scrolling region while its validation and Start bar remain fixed at the
bottom.

## Results

no measurements — implementation only

The debug and release builds passed. In the rebuilt application, RFdiffusion3 was
selected through the real workflow picker in a 1400 by 850 point window. The picker
remained visible, the form opened at its header with a dedicated vertical scrollbar,
and the bottom validation/Start bar remained inside the window.

## Decision and rationale

The detail viewport owns the height constraint. Constraining only individual controls
would leave every future tall workflow vulnerable to the same split-view ideal-size
behaviour. Replacing the workflow's internal scroll view with a single root scroll view
was rejected because the workflow picker and run controls are intentionally persistent.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
env CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swift-cache \
  caffeinate -dimsu swift build
caffeinate -dimsu ./build_app.sh release
open build/iProteinStudio.app
```

Select a design project, click **RFdiffusion3**, resize the window to approximately
1400 by 850 points, and confirm that the workflow picker remains visible while the
form has its own vertical scrollbar and the Start bar remains fixed.

## Limits and what was not tested

The regression was checked on one Apple Silicon Mac, one display scale and one
representative window size. VoiceOver, full keyboard traversal, extreme minimum window
sizes and multiple macOS releases were not tested. No RFdiffusion3 model job was run;
this change affects layout only.

## Next

Add a UI test harness that can assert the workflow picker and scroll view frames after
switching to RFdiffusion3 at the minimum supported window size.
