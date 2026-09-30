---
entry: 0232
title: Select one adopted-code baseline per model for the paper comparison
date: 2026-09-30
author: Codex
type: decision
status: complete
machine: Historical measurements reviewed from Apple M4 Max, 40-core GPU, 64 GB, macOS26.6.1
tags: [benchmark, paper, predictors]
---

## Context
User prefers one obvious baseline per model, community port where adopted, and asks which existing evidence supports our interventions and what single summary comparison to run. Revises0231; no new predictions requested.

## What was done
Reviewed original runtime screens0168–0171, recent0228/0229/0230, Constraint0045 and current campaign records. Added `Validation/experiments/mac_intervention_baselines_v1/SINGLE_BASELINE.md`, revised research manifest to two arms, and marked the old three-stage figure proposal superseded. Corrected the earlier report's description of3QHT: it is a bound reference. Preserved existing raw outputs and evidence snapshot.

## Results
No new measurements — research only. Nine baseline/after rows explicitly identify source, historical dependency version and common minimal Mac fixes. OpenFold/ESM use adopted community source as the baseline; PyTorch-to-MLX gains are excluded from our contribution. Distinguish large qualified padding/lifecycle changes, small changing-binder gains, memory effects and negative/failed changes. No combined speedup is inferred by multiplying historical ratios.

## Decision and rationale
Single two-arm comparison: five existing SUMO binder lengths×five seeds, plus five monomer seeds per arm/model; native diffusion budgets,128-row target MSA, query-only binders, Fast sequence-only. Nine models,540 measured outputs plus warmups, five counterbalanced process blocks. Native same-process/directory reuse allowed in baseline. Cold initialization separate from warm throughput. Existing isolated initialization shortcut excluded from OpenFold after endpoint. ESM memory benefit is not asserted to be speed benefit. Constraint baseline OOM remains OOM without inventing a ratio or changing control.

## Reproduce
Read SINGLE_BASELINE.md and manifest.json. Historical timings link to original project/Validation entries and raw reports. Evidence file from0231 remains unchanged. Future isolated environment locks and paired input/timing plan still required before managed broker execution.

## Limits and what was not tested
No inference, installs, workers/job changes, numerical tests, app edits, Swift build, commit or release. Historical data are different cohorts/timing boundaries and do not replace the complete-stack paired comparison. Current broad campaign supplies after-only evidence and is incomplete. No universal chip/target or wet-lab accuracy claim. Read/audited JSON model count, native settings and540-output arithmetic.

## Next
Present the baseline/evidence table and two-arm comparison. Execute only after a future instruction to run it; retain ongoing campaign priority.
