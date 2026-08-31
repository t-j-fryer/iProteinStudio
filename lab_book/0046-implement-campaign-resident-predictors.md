---
entry: 0046
title: Implement campaign-resident iterative predictors
date: 2026-08-30
author: codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, persistence, boltz, intellifold, protenix, mps]
---

## Context

Entry [[0045-validate-cycle-waves-before-residency]] established that directory
replay was not true residency. The requested benchmark is now deliberately
narrow: current per-trajectory execution versus one process per cycle versus one
live model across the complete campaign, using 12 trajectories, five redesign
cycles and fixed 80-aa binders. Helix suppression and experimental IntelliFold
padding are excluded.

## What was done

- Added a checksummed file-queue worker in `scripts/resident_predictor.py`. The
  campaign shell remains authoritative for state, MPNN redesign, resume and
  output normalization.
- Boltz retains one `Boltz2` object while reusing its pinned input processing,
  Lightning prediction and writer path for each cycle request.
- IntelliFold retains one MPS model and Accelerator while rebuilding only the
  upstream processed inputs and dataloader for each request.
- Protenix retains one `InferenceRunner` and swaps request-local input JSON,
  dumper and error directories without reloading the checkpoint.
- Added `--design-scheduler resident`, restricted it to one all-trajectory wave
  and one MPS process, and required exact request checksums, output cardinality,
  worker PID and model-load count.
- Kept the worker as a normal campaign child. A double-fork prototype lost its
  macOS `MTLCompilerService` connection and was rejected.
- Fixed a pre-existing Protenix-to-MPNN handoff bug uncovered by the smoke:
  `normalize_unk_cif.py` printed a diagnostic to stdout, which command
  substitution prepended to the designed sequence. Diagnostics now use stderr,
  and every inverse-folding handoff is alphabet- and length-validated.
- Narrowed the governed SUMO matrix to 18 campaigns (six engines by three
  schedulers), one sample/seed, one fixed 80-aa binder length and no helix or
  padding contrast. Added wall-time, phase-time, startup and load-count tables
  plus transparent Arial SVGs for wall time and speedup.

## Results

Native-MPS implementation smokes completed on this machine. Startup is measured
through the worker readiness receipt; request wall time includes request-local
feature processing, inference, confidence annotation and normalization.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Protenix Mini, one resident model, cycle 00 then MPNN then cycle 01 | 2 requests | startup; request walls | 8.97 s; 5.79 s, 2.18 s |
| Boltz 2, same two-request route | 2 requests | startup; request walls | 10.81 s; 13.62 s, 13.27 s |
| IntelliFold v2-flash, same two-request route | 2 requests | startup; request walls | 4.15 s; 37.66 s, 34.34 s |
| Protenix v2 resident checkpoint smoke | 1 request | startup; request wall | 25.71 s; 42.66 s |
| Protenix Constraint v0.5 resident checkpoint smoke | 1 request | startup; request wall | 27.95 s; 34.61 s |
| IntelliFold full v2 resident checkpoint smoke | 1 request | startup; request wall | 5.70 s; 143.39 s |

Every successful request receipt reported `model_load_count=1`; every smoke
emitted one normalized structure and confidence record per requested input. The
Boltz log contained its separately documented `aten::linalg_svd` CPU fallback;
no other fallback was allowed. The first Mini prototype never reached inference
after daemonization broke Metal compiler service access. The next prototype
completed cycle 00 and then exposed the stdout contamination bug. The third
completed both requests and is the reported result.

The complete paired campaign then finished with 1,080/1,080 optimized cycle
structures (cycle 00 excluded) and no receipt-level audit errors:

| Engine | Current | Cycle-wave | Resident | Selected |
|---|---:|---:|---:|---|
| Boltz 2 | 40.26 min | 28.35 min | **22.07 min** | resident |
| IntelliFold v2-flash | 47.01 min | 38.52 min | **38.05 min** | resident |
| IntelliFold full v2 | 170.35 min | 153.63 min | **151.04 min** | resident |
| Protenix v2 | 84.96 min | **70.44 min** | 79.93 min | cycle-wave |
| Protenix Mini | 20.39 min | 4.94 min | **4.54 min** | resident |
| Protenix Constraint | 66.43 min | 42.65 min | **40.09 min** | resident |

Model loads were 72, 6 and 1 for current, cycle-wave and resident arms.

## Decision and rationale

New campaigns now default to an engine-specific Optimized policy: resident for
all iterative design engines except full Protenix v2, which uses cycle-wave.
Compatibility mode retains the old process-per-trajectory route.

Protenix v2 is not assigned residency because its resident model-forward mean
rose to 65.14 s versus 55.30 s in cycle-wave, despite bounded 2.75--2.82 GB MPS
allocation. A paired check found that the accidentally inherited IntelliFold
single-thread environment explained only about 3% and was not the cause; that
environment is now applied to IntelliFold alone. Sustained-load power/thermal
or MPS process-lifetime effects are plausible but unproven because telemetry
was not collected.

## Reproduce

```bash
bash Tests/test_iterative_cli_contract.sh
python3 Validation/experiments/resident_design_v1/campaign.py plan \
  --output Validation/output/resident_design_v1/three_mode_80aa
caffeinate -dimsu python3 Validation/experiments/resident_design_v1/campaign.py run \
  --output Validation/output/resident_design_v1/three_mode_80aa
```

## Limits and what was not tested

The result covers SUMO, 80-aa protein binders, one seed/sample and this M4 Max.
Nanobodies, ligands, mixed lengths, post-predictor stages, other Apple chips,
randomized scheduler ordering, temperature/power telemetry, interruption and
worker-death injection remain outside the evidence. Boltz's known SVD fallback
is counted rather than described as fully MPS-native. An upstream directory
runner can advance one RNG stream across ordered inputs, so the optimized arms
are comparable to one another but are not claimed to be bit-identical to the
independently restarted current arm.
