---
entry: 0089
title: Summarize the completed secondary-structure control experiment
date: 2026-09-04
author: gpt-6
type: analysis
status: complete; no default promotion
machine: Apple M4 Max / 64 GB (campaign provenance)
tags: [validation, secondary-structure, anti-helix, beta-sheet]
---

## Work and evidence

The user requested the experiment results. All five previously submitted full
arms are completed; audited 300 structures (50 cycle-00 starts plus 250 optimized
outputs). Ran the declared coordinate-based P-SEA analysis and added/executed a
reproducible sequence/coordinate/confidence audit and paired summary script.

The detailed method, launch/engine provenance references, device-log audit,
results, intervals, exact statistical unit and reproduction commands are in
[Validation entry 0007](../Validation/lab_book/0007-secondary-structure-comparison-results.md).

## Results and decision

Across optimized cycles 01–05, sustained anti-helix reduces helix by 11.56
percentage points relative to its identical-start seed-only control (paired
bootstrap interval: 4.27–20.42 points reduction; 9/10 trajectory pairs decrease).
Coil increases by 11.20 points, while sheet changes only +0.36 points. The
intervention suppresses helix predominantly toward coil, with lower mean binder
confidence.

Sustained beta increases sheet by only 0.84 points relative to beta seed-only
(interval -3.60 to +6.31). Beta enrichment is not established. Keep the priors
experimental; no default is promoted.

## Limits and what was not tested

One target, 90-residue binders, 0.50 strengths and 10 paired trajectories per arm.
No independent predictor, wet-lab test, sequence-diversity analysis, detailed
geometry audit, cross-target replication or speed benchmark. Cycle 00 is excluded
from optimized endpoints, and cycles are not treated as independent replicates.
Existing scientific jobs and raw outputs were not modified or resubmitted. No
app/runtime changes, build or commit were needed for this analysis.
