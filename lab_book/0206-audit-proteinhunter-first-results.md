---
entry: 0206
title: Audit Protein Hunter startup and first-result visibility
date: 2026-09-28
author: Codex
type: audit
status: complete
machine: source inspection only
tags: [predictors, ui]
---

## Context

User asked what happens when Protein Hunter starts with Boltz, when binders
appear, and what status information the app currently exposes.

## What was done

Traced CommandBuilder scheduling, managed broker messages, nanohunter_run.sh
startup/resident cycle waves, RunResultsLoader, MetricsWatcher, and
JobProgressView. No campaign or implementation was changed.

## Results

No measurements — source audit only. Default app Boltz scheduling requests one
resident worker and a directory request containing all trajectories in each
cycle. Target MSA preparation precedes calibration and campaign model loading.
The default command does not pass --skip-predictor-calibration: an explicit
--max-parallel 1 does not itself skip calibration. Calibration is not a displayed
design result.

The resident loop reports changed completed/total counts at ten-second polling
intervals and a still-running message every minute. Initial model loading emits
a waiting message every thirty seconds. These are log updates, not an accurate
GPU percentage. The main managed status is coarser (queue/engine/stage).

record_cycle_wave_predictions runs only after all prediction batches in a cycle
finish. The app reads its metrics_per_cycle.csv output, so cycle00 starting
structures appear after the whole initial wave, not after the first raw model
file. Cycle01 sequence-designed complexes appear after the next completed wave.
Embedded results and metrics poll at two seconds; saved-run results at three.
Hits require independent validation and saved filter verdicts.

## Decision and rationale

Explain current behavior accurately, including delayed display and coarse main
status. Do not claim per-prediction live visibility or universal time estimates.
Incremental publication would improve responsiveness without changing inference.

## Reproduce

Inspect Sources/iProteinStudio/Core/CommandBuilder.swift,
Core/Results/RunResultsLoader.swift, Core/MetricsWatcher.swift,
Views/JobProgressView.swift, and Resources/pipeline/nanohunter_run.sh functions
submit_resident_predictor_request and run_designs_cycle_wave.

## Limits and what was not tested

No new run, UI interaction, timing measurement, or model test. Older retained
campaign snapshots and explicitly selected CLI schedulers can behave differently.

## Next

If requested, publish durable per-prediction results and promote completed/total
counts into the main status display, preserving wave scheduling and resume rules.
