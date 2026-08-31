---
entry: 0046
title: Implement campaign-resident iterative predictors
date: 2026-08-30
author: codex
type: implementation
status: in-progress
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

## Decision and rationale

The implementation is ready for the requested paired full-campaign benchmark,
but is not an app default. A persistent Python object is insufficient evidence
by itself; promotion depends on end-to-end wall time, exact outputs, interruption
and memory behavior in the complete 12 by five setting.

## Reproduce

```bash
bash Tests/test_iterative_cli_contract.sh
python3 Validation/experiments/resident_design_v1/campaign.py plan \
  --output Validation/output/resident_design_v1/three_mode_80aa
caffeinate -dimsu python3 Validation/experiments/resident_design_v1/campaign.py run \
  --output Validation/output/resident_design_v1/three_mode_80aa
```

## Limits and what was not tested

The complete 18-campaign comparison has not yet completed. Smokes cover SUMO,
80-aa protein binders, one seed/sample and this M4 Max. Nanobodies, ligands,
other lengths and Apple chips remain outside the evidence. Boltz's known SVD
fallback is counted rather than described as fully MPS-native.

## Next

Freeze the exact commit/runtime hashes, launch the 18 paired campaigns under
`caffeinate`, audit all 1,296 requested structures (including cycle 00), and
generate the declared speed figures before considering any default change.
