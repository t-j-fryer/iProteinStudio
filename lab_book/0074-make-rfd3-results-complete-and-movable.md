---
entry: 0074
title: Make RFdiffusion3 results complete, live and movable
date: 2026-09-02
author: gpt-5.6-sol
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [rfd3, results, swiftui, boltz, apo, provenance]
---

## Context

The completed GUI campaign `rfd3-20260902-220705` could be opened from Run
history, but the RFdiffusion3 page's own live-results action appeared inert.
Results launched from history were sheets attached to a narrow popover, so they
opened against the side of the main window and could not be moved independently.
The browser showed the complex predictions but not the ligand-free folds, and
labelled the old ligand campaign's prediction engine only as “Prediction”. This
followed [[0067-add-live-rfd3-results-and-exact-motif-recovery]] and the
cross-modal audit in [[0073-audit-executable-workflows-across-modalities]].

## What was done

- Replaced results sheets launched from RFdiffusion3, Activity/Run history,
  Predict, iterative design and the prediction library with one typed SwiftUI
  `WindowGroup`. Results now open in a normal resizable and movable macOS window.
- Made **Browse Live Results** available immediately. An empty live window shows
  its waiting state and refreshes as backbone and predictor checkpoints arrive.
- Kept generated MLX backbones visible after ranking instead of replacing them
  with only the selected verification structures.
- Joined ranked manifests to both `predictions/holo` and the protein
  `predictions/monomer` or ligand `predictions/apo` tables. Complex and
  binder-alone structures are separately named and retain per-engine confidence
  and apo–holo RMSD where available.
- Added backward-compatible Boltz-2 provenance for old ligand campaigns, whose
  dedicated Boltz runner made the engine implicit. New rows and run manifests
  now persist `predictor=boltz` plus `prediction_context=complex|binder_alone`.
- Changed the detail caption from the ambiguous “scores reported by” wording to
  explicit generation or prediction provenance.
- Renamed the progress count from “Apo folds” to “Binder-alone folds”.

## Results

No new prediction or performance measurement was run; this was presentation and
durable-provenance repair. The loader was executed against the user's real
completed campaign rather than only a synthetic fixture.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Existing fluorescein campaign | 8 | generated MLX backbones discovered | 8/8 |
| Same | 16 | complex Boltz-2 structures discovered | 16/16 |
| Same | 16 | ligand-free Boltz-2 structures discovered | 16/16 |
| Same | 40 | result items with explicit source | 40/40 |

The real campaign's existing log and checkpoint table independently record that
all 16 ligand-free folds completed. The apparent omission was therefore confined
to result discovery and presentation.

## Decision and rationale

Results are documents, not transient confirmation dialogs. A separate typed
window was chosen over increasing sheet size because a sheet remains anchored
to its parent and cannot be freely positioned. The same window route is shared
by every workflow to prevent another workflow-specific presentation drift.

The loader joins durable checkpoint tables instead of rewriting old user runs.
New runs persist explicit engine/context fields at emission time; inference from
the known Boltz-only legacy runner is retained solely for backward compatibility.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

bash Tests/test_rfd3_results_ui_contract.sh
~/.iproteinstudio/rfd3/.venv/bin/python Tests/test_workflow_pipelines.py
python3 -m unittest Tests/test_rfd3_predictor_scheduling.py

CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-swift-cache \
SWIFT_MODULECACHE_PATH=/tmp/iproteinstudio-swift-cache \
swiftc Tests/PredictionResultsContractHarness.swift \
  Sources/iProteinStudio/Models/RunResult.swift \
  -o /tmp/prediction-results-contract
/tmp/prediction-results-contract
/tmp/prediction-results-contract \
  /Users/thomasfryer/.iproteinstudio/projects/untitled_design/rfd3_runs/rfd3-20260902-220705

swift build
```

The real-campaign loader prints:

```text
RFD3_RESULTS|total=40|backbones=8|complexes=16|binders=16|sources=Boltz-2, RFdiffusion3 MLX
```

## Limits and what was not tested

- The new window was compiled but not opened and dragged through GUI automation;
  this repository has no macOS UI-test target that can drive multiple scenes.
- No new heavy RFdiffusion3 or Boltz inference was launched. The exact completed
  campaign supplied by the user was inspected and loaded from disk.
- Protein-target monomer discovery is covered by the shared schema and existing
  scheduling contracts, but this change did not launch a fresh partial or motif
  campaign through every verification engine.
- Existing small-molecule campaigns do not gain new columns on disk. Their
  Boltz-only source is labelled through the backward-compatibility rule.

## Next

Open the rebuilt app, start a one-backbone smoke, open Browse Live Results before
the first backbone lands, then drag and resize the results window. After the
campaign completes, confirm that backbone, complex and binder-alone entries stay
visible in that same window.
