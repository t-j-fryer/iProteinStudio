---
entry: 0116
title: Add measured campaign time per design to overview figures
date: 2026-09-09
author: Codex
type: audit
status: complete
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1 (original measurements)
tags: [analysis, figures, timing, provenance]
---

## Context

The user requested time per design on the overview figures for the complete v7
binding and v3 monomer analyses. This is retrospective analysis of existing
measurements; no campaign or model inference was launched and no raw job changed.

## What was done

Added one timing panel per overview, a shared audited timing helper, `timing.csv`
and `timing.json`, a seconds-per-design column in `summary.csv`, and matching
report/gallery captions. Regenerated SVG/PNG/PDF overviews, combined PDFs,
self-contained galleries, artifact checksums and downloadable ZIP packages.
Other scientific endpoints and their statistical units are unchanged.

## Definition and rationale

Seconds per optimized design = summed pilot and remaining design-stage spans / 50 completed cycle01–05 outputs (10 trajectories × 5 cycles). Each phase span is latest trajectory end minus earliest trajectory start; overlapping resident-worker timers are counted once. Includes initialization, MPNN and gaps within the recorded span; excludes queueing and setup before the first trajectory timer. This is amortized elapsed time, not individual prediction latency. One aggregate per condition from two unequal phases (1 + 9 trajectories); no timing CI. Apple M4 Max, 64 GB, macOS 26.6.1; native settings differ across engines, so these are descriptive campaign costs, not a controlled engine speed comparison.

The native resident/cycle-wave runs have overlapping per-trajectory timers.
Summing or averaging those durations would confuse trajectory latency with
throughput. We instead aggregate the measured phase span once, combine the
one-trajectory pilot with the nine-trajectory remaining phase, and divide by
50 completed optimized outputs. Cycle00 is included in elapsed cost but is never
counted as a design. This does not infer pure GPU inference time or provide
independent timing replicates or error bars.

## Results

The table below is derived from the existing hash-verified `timing_run.csv`
measurements on Apple M4 Max, 64 GB, macOS 26.6.1; units are seconds per optimized
design. These are historical campaign costs, not new benchmark measurements.

| Engine | Binding h0 | Binding h1 | Monomer h0 | Monomer h0.5 | Monomer h1 |
|---|---:|---:|---:|---:|---:|
| boltz | 43.4 | 40.7 | 22.2 | 21.6 | 21.1 |
| intellifold_flash | 36.3 | 36.6 | 28.8 | 29.1 | 29.2 |
| intellifold_full | 156.7 | 157.2 | 66.0 | 64.9 | 62.8 |
| protenix_v2 | 61.7 | 61.5 | 54.7 | 54.6 | 54.6 |
| protenix_mini | 3.4 | 3.4 | 18.5 | 18.4 | 18.4 |
| protenix_constraint | 29.7 | 30.1 | 56.6 | 56.5 | 56.5 |
| openfold3 | 64.9 | 64.8 | 58.0 | 57.6 | 58.4 |

## Provenance and controls

Analysis source worktree HEAD: `37cc95497283025191e7d2067cb35d1af9168d72` (dirty).
The original manifests, stage receipts and audit hashes retain engine/checkpoint,
seed, native-step/recycle, MSA and scheduler identities. No settings are promoted.
Both studies use 90-aa binders, initialization-only strengths, and five optimized
cycles. Binding uses the frozen ACBX target alignment with SHA-256
`377a3af41f6816683c9b06241fafd2e0c2bc6b0129c2f4a78387ad36f75f34cf`;
the monomer study uses explicit empty MSA. Strengths remain separate conditions,
not speed controls. `integrity.json` adds the timing-helper hash and all timing
source hashes. The complete raw/coordinate reassessment is rerun by each script.

## Reproduce

From the canonical repository root:

```bash
MPLCONFIGDIR=/private/tmp/binder-helix-timing-mpl "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" Validation/experiments/binder_helix_strength_full_analysis_v1/analyse.py
MPLCONFIGDIR=/private/tmp/helix-timing-mpl "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" Validation/experiments/helix_strength_full_analysis_v1/analyse.py
MPLCONFIGDIR=/private/tmp/binder-helix-timing-mpl "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" -m unittest discover -s Validation/experiments/binder_helix_strength_full_analysis_v1 -p 'test_*.py' -v
MPLCONFIGDIR=/private/tmp/helix-timing-mpl "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" -m unittest discover -s Validation/experiments/helix_strength_full_analysis_v1 -p 'test_*.py' -v
```

## Limits and what was not tested

No new neural inference, performance experiment, M1 test, binding test or app
build was performed. The timestamps do not isolate GPU kernels, pre-timer setup,
queue waits or active compute from any pauses within a recorded span. Different
sequences and native engine settings preclude a controlled cross-engine speed
claim. Geometry and confidence endpoints retain the original interpretation.

## Validation status

Timing-accounting fixtures passed for overlapping timers, within-phase gaps,
phase weighting, output cardinality, invalid durations and corrupted source hashes.
Both full analyses regenerated successfully: 840 binding complexes and 1,260 monomer structures reassessed, with all frozen raw hashes verified. Binding analysis tests (3) and monomer/statistical/timing tests (7) passed. Both PNG overviews were visually inspected. Each package has 26 verified artifact hashes plus its hash manifest and ZIP; archive bytes and gallery-embedded SVGs match the regenerated files. All 350 trajectory timing sources are audited across 35 conditions. No original raw output was modified.
