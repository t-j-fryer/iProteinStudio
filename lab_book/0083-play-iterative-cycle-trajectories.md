---
entry: 0083
title: Play target-aligned iterative cycle trajectories
date: 2026-09-03
author: gpt-5.6
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, results, iterative, py2dmol, validation]
---

## Context

After Entry `[[0082-nest-result-derivatives]]`, each iterative run displayed its
cycles cleanly but only one structure at a time. py2Dmol already had a frame
scrubber, play button and playback-speed control, so the missing piece was a
scientifically meaningful multi-frame object. Directly adding each predictor
output as a frame would animate arbitrary global rotations and translations
rather than optimization progress.

## What was done

- Added one ordered design-stage trajectory per iterative run: cycle 00, then
  each optimized cycle. Independent complex and binder-alone verification folds
  are deliberately excluded because they are checks, not optimization states.
- Added a `Trajectory` option to the structure picker at the top right of the
  run detail. Individual design and verification structures remain selectable.
- Added a multi-frame bridge from Swift to the vendored py2Dmol viewer. The
  existing bottom slider, Play and speed controls operate on these frames.
- Labelled the frame counter with `Starting structure`, `Cycle 01`, and so on,
  instead of showing only anonymous frame numbers.
- Before display, fitted every later frame to cycle 00 using common target Cα
  atoms on chains B onward. Binder chain A and ligands do not influence the fit.
- Made alignment fail closed if either frame has fewer than three common target
  Cα atoms.
- Replaced use of py2Dmol's historical `align_a_to_b` helper after the real
  WebKit test showed that its notebook-only `numeric` dependency is not exposed
  by the vendored browser bundle. Studio now uses a dependency-free Horn
  quaternion rigid fit with a symmetric 4×4 Jacobi eigensolver.
- Added a native WebKit harness that exercises the shipped HTML/JavaScript,
  verifies a rotated synthetic rigid fit, loads two real iterative-cycle CIFs,
  confirms the target fit improves, and checks the labelled two-frame scrubber.

## Results

No predictor inference or performance measurements — existing saved structures
were used for functional validation.

| Condition | n | Result |
|---|---:|---|
| Synthetic rotated coordinate fit | 4 points | maximum residual below `1e-8` Å |
| Supplied iterative campaign, run 1 | 2 real cycle CIFs | WebKit trajectory loaded; 71 common target positions; fitted RMSD improved; labelled slider exposed two frames |
| Supplied iterative campaign | 12 runs / 72 cycles | all 12 runs expose ordered six-frame design trajectories |
| Native Swift build | 1 | pass |
| Iterative and RFD3 result contracts | 2 | pass |

## Decision and rationale

The target is the stationary reference for binder optimization, so fitting on
target chains makes binder motion and fold changes interpretable. Fitting on the
whole complex would partially erase binder movement; fitting on binder A would
erase exactly the behavior the trajectory is meant to show.

The trajectory remains a presentation transform. Saved coordinates are neither
rewritten nor replaced, and selecting an individual structure still opens the
unaltered file and its scores.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-swift-cache \
SWIFT_MODULECACHE_PATH=/tmp/iproteinstudio-swift-cache \
swiftc -parse-as-library Tests/Py2DmolTrajectoryHarness.swift \
  -framework AppKit -framework WebKit \
  -o /tmp/iproteinstudio-py2dmol-trajectory

/tmp/iproteinstudio-py2dmol-trajectory \
  Sources/iProteinStudio/Resources/web/py2dmol/viewer.html \
  /Users/thomasfryer/Downloads/untitled_prediction_2/run_001/cycle_00/pred_min/model_0.cif \
  /Users/thomasfryer/Downloads/untitled_prediction_2/run_001/cycle_01/pred_min/model_0.cif

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-swift-cache \
SWIFT_MODULECACHE_PATH=/tmp/iproteinstudio-swift-cache \
swiftc Tests/PredictionResultsContractHarness.swift \
  Sources/iProteinStudio/Models/RunResult.swift \
  -o /tmp/iproteinstudio-results-contract
/tmp/iproteinstudio-results-contract iterative \
  /Users/thomasfryer/Downloads/untitled_prediction_2

bash Tests/test_iterative_results_ui_contract.sh
bash Tests/test_rfd3_results_ui_contract.sh

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iproteinstudio-swift-cache \
swift build --disable-sandbox --scratch-path /tmp/iproteinstudio-build
```

## Limits and what was not tested

The complete six-frame inventory was checked for all 12 supplied runs, while the
full WebKit rendering path was exercised on run 1 cycles 00 and 01. Autoplay and
slider construction were exercised programmatically, but playback timing was
not benchmarked and the animation has not yet been manually inspected on the M1
Mac. The alignment assumes Studio's enforced iterative convention: binder chain
A and target protein chains B onward.

## Next

Manually inspect a full six-cycle trajectory on both development and M1
hardware. Add synchronized camera state between individual structures only if
the target-fitted animation does not already provide the needed comparison.
