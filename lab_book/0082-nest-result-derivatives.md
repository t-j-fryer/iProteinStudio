---
entry: 0082
title: Nest derivatives and cycles in clean result groups
date: 2026-09-03
author: gpt-5.6
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, results, iterative, rfd3, validation]
---

## Context

Entry `[[0081-group-related-design-results]]` grouped related structure files,
but flattened an RFdiffusion3 backbone and each MPNN derivative into peers when
reading newer campaign manifests. Those manifests legitimately store a
derivative such as `design_0002_1` in `design`, while the source file remains
`rfd3/backbones/design_0002.pdb`. The old regression fixture used the earlier
schema, where `design` was already the unsuffixed backbone, and did not expose
the fault.

The horizontal comparison strip also put a full py2Dmol control panel inside
each 320-point card. Its fixed 190-point panel left too little canvas and made
the controls appear to overlap the useful structure area.

## What was done

- Added an explicit child identity to the result model. A top-level group is an
  RFdiffusion3 backbone or iterative run; a child is an MPNN derivative or
  iterative cycle.
- Made `backbone_pdb` the preferred durable RFD3 parent identity, with compatible
  handling of old and new `design`/`seq_index` schemas. The UI no longer guesses
  the parent solely by trusting the overloaded manifest `design` field.
- Paired complex and binder-alone predictions inside each MPNN derivative. The
  source MLX backbone stays visible once at the top of its parent.
- Grouped iterative results first by run and then by cycle. The design-stage,
  independent complex and binder-alone artifacts remain paired within a cycle.
- Made the Hits view retain parent context but show only passing child
  derivatives/cycles.
- Changed overview score distributions and hit counts to use one value/verdict
  per child derivative or cycle rather than one arbitrarily selected value per
  parent backbone/run.
- Replaced the row of small control-heavy viewers with control-free structure
  previews and one large selected interactive py2Dmol viewer. Clicking a preview
  or choosing its labelled role opens it in the large viewer with full controls.
- Expanded the results window's minimum and ideal size so the interactive
  canvas and its control panel have separate usable space.
- Updated the synthetic contract to use the newer RFD3 manifest schema and
  checked both supplied real campaigns.

## Results

No inference or performance measurements — result-model and UI implementation
only.

| Condition | n | Result |
|---|---:|---|
| Supplied moved iterative campaign | 12 runs / 72 cycles / 192 artifacts | one saved run-12/cycle-5 hit retained; 60 complete design + complex + binder comparisons |
| Current Cbx RFD3 campaign (`acbx_1ctx_surface_ema_smoke5`) | 5 backbones / 10 MPNN derivatives / 25 artifacts | all 10 derivatives contain paired complex and binder-alone predictions beneath the correct backbone |
| New-schema synthetic RFD3 fixture | 1 backbone / 1 derivative / 3 artifacts | derivative `design_0001_0` nested under `design_0001` from `backbone_pdb` |
| Native Swift build | 1 | pass |
| Iterative and RFD3 results UI contracts | 2 | pass |

## Decision and rationale

Parent structure generation and sequence-derived validation are distinct levels,
so the presentation model now records both rather than reconstructing hierarchy
from names in the view. The score distribution uses the independently evaluated
child as its unit: collapsing two MPNN sequences into one backbone value would
hide real variation, while counting the complex and binder-alone files
separately would duplicate a single derivative.

Only one full-control WebKit viewer is instantiated as the main inspection
surface. Comparison cards remain visual and clickable but omit controls. This
keeps the complex/binder pair visible together without squeezing a renderer and
a fixed-width tool panel into every thumbnail.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-swift-cache \
SWIFT_MODULECACHE_PATH=/tmp/iproteinstudio-swift-cache \
swiftc Tests/PredictionResultsContractHarness.swift \
  Sources/iProteinStudio/Models/RunResult.swift \
  -o /tmp/iproteinstudio-results-contract

/tmp/iproteinstudio-results-contract
/tmp/iproteinstudio-results-contract iterative \
  /Users/thomasfryer/Downloads/untitled_prediction_2
/tmp/iproteinstudio-results-contract \
  /Users/thomasfryer/.iproteinstudio/projects/untitled_design/rfd3_runs/acbx_1ctx_surface_ema_smoke5

bash Tests/test_iterative_results_ui_contract.sh
bash Tests/test_rfd3_results_ui_contract.sh

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iproteinstudio-swift-cache \
swift build --disable-sandbox --scratch-path /tmp/iproteinstudio-build
```

## Limits and what was not tested

No new RFdiffusion3, MPNN or folding inference was run because the scientific
pipelines and saved files were not changed. The supplied real iterative and
current new-schema RFD3 campaigns were parsed end to end, and the app compiled.
This pass did not manually click every viewer control, test VoiceOver, or inspect
the result window on the M1 Mac. The preview layout is adaptive, but its minimum
supported-window appearance still merits a manual second-machine check.

## Next

On the M1 Mac, open both the supplied iterative campaign and a current RFD3
campaign, verify the adaptive pair layout at the user's preferred window size,
and consider synchronized camera orientation only if direct pose comparison
still benefits from it.
