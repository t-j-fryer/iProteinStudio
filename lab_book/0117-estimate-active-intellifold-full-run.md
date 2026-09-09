---
entry: 0117
title: Estimate remaining time for the active IntelliFold Full campaign
date: 2026-09-09
author: Codex
type: audit
status: complete
machine: Current managed Apple GPU run; hardware was not re-probed
tags: [timing, predictors, status]
---

## Context

The user requested an ETA for their currently active Studio run. This was a
read-only inspection; no job, configuration, engine or model was changed.

## Evidence and results

Observed at 2026-09-09T13:06:36.251960-04:00. Job `job-4d54e18d450b` reports
IntelliFold v2 Full, engine 6 of 7. The request specifies 50 trajectories × 5
optimization cycles, plus 50 starting folds: 300 predictions total. The resident
readiness receipt confirms model `v2`, MPS, fallback 0 and model_load_count 1.

The completed cycle00 batch took 11,754.000196 seconds for 50 predictions.
Cycle01 has 20 written CIFs with accompanying summary-confidence files; the
wave has not yet completed its downstream audit. Its observed pace is
260.1754 seconds per written structure from submission, with the last ten
completion intervals averaging 270.7640 seconds. There are 230 predictions
remaining. This supports approximately 17 hours remaining, with a practical
15–18-hour range (roughly 04:00–07:00 EDT on September 10). The estimate is for
IntelliFold only. OpenFold3 is still next and has no current-campaign calibration
or outputs yet; no equally reliable whole-batch ETA was claimed.

## Method and provenance

Campaign: `/Users/thomasfryer/.iproteinstudio/projects/untitled_design/untitled_design_intellifold_full_6ed978fa`.
Read `studio_run.json`, `_cycle_wave/predictor_batches.csv`, resident request and
ready receipts, the active broker `state.json`/`pipeline.log`, and cycle01 CIF
modification times with corresponding summary-confidence files. Used CIF
completion times because completed-cycle confidence files can be rewritten by
postprocessing and their mtimes are not reliable individual inference timers.
No summation of overlapping trajectory durations was used.

The normal `studioctl.py jobs` command attempted to refresh state and was blocked
by the filesystem sandbox. Continued by reading the persisted state and live
artifacts directly; no registry files were written or process status altered.

## Limits and what was not tested

This is an extrapolation of the running campaign, not a new benchmark. Remaining
cycles may differ in cost, and later model timings are not measured yet. Written
active-wave artifacts were counted for progress, not certified as final hits.
No inference, restart, cancellation, software change or package build was run.

## Next

Refresh from the next completed wave if a tighter ETA is needed.
