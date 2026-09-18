---
entry: 0148
title: Launch the approved biotin campaign without partial noising
date: 2026-09-17
author: Codex
type: experiment
status: in-progress
machine: Apple M4 Max, 64 GB unified memory
tags: [nise, biotin, campaign, resident]
---

## Context

After reviewing the revised settings in0147 and the purpose of the backbone RMSD
gate, the user explicitly requested starting the run. Partial noising is disabled.
The previous noising-enabled full plan and failed five-start pilot remain unchanged.

## What was done

Read the MCP workflow guide, detected installed engines through the fresh source
bridge and checked the queue. Boltz structure, affinity and LASErMPNN all report
`ok`; no jobs were running or queued. Created a fresh `nise_plan`, added a saved
display label before final immutable planning, verified exact equality with the
0147 reviewed draft, and submitted the final digest through MCP `job_start`.
The shared execution lock, frozen scripts/inputs/model fingerprints, resident
scheduler and empty-MSA policy remain in force.

Name: **Biotin — 1000 starts — Boltz NISE**; project `test2`.

- Plan: `plan-002ee4e5c61e272f`.
- SHA256: `002ee4e5c61e272f5f4511fb554b90041f73a4681c1a6612140d4dcb752c47aa`.
- Job: `job-002ee4e5c61e`.
- Run: `test2/nise_runs/nise-7345aaf6c30d1a9e` under the managed projects directory.
- Source: commit `f6ca410`; subsequent working-tree changes are Lab Book records.

Saved request, complete final plan, detection, launch and startup evidence are in
[artifacts/0148-launch-biotin-without-noising](artifacts/0148-launch-biotin-without-noising/).
A `studio_job.json` associates the native app's run with the broker job.

## Results

Broker reports `running`, no error. The resident worker is ready on MPS with
fallback disabled, initial model-load count1 and PID76818. The pipeline entered
Phase0 cycle00 with1000 starts and the reviewed nine-atom pocket restraint.
The first initial prediction, `L000`, completed and its structure-phase operation
receipt was archived. Broker remains running with no error. This is a launch
verification, not a completed campaign or a performance result.

Settings:1000 starts,65–150 residues, Protein Hunter initial generation; up to8
independent seed lineages; beam3;64 first-cycle proposals then32 per parent
(up to96 per trajectory/cycle); max30 cycles; patience4; improvement>0.01.
Partial noising, adaptive sampling, NESSO and apo analysis off. Initial refinement
gate0.80; backbone RMSD<2.5 Å during optimization; ligand RMSD<2.5 Å from cycle3;
nine head hotspots within6 Å; only O18/O19 exposure>=50%; geometry-first selective
affinity; score ligand pLDDT/100+P(bind). Exact stage settings are in the request.
Calculated maximum47,784 structure predictions; no wall-time estimate inferred.

## Decision and rationale

Use the newly approved noising-free request, never the old held noising plan.
Prior evidence includes the completed ordinary biotin campaign and the bounded
one-parent real-model test in0145, which exercised MPNN, Boltz structure/affinity,
geometry checks and residence. The five-start pilot's early-gate attrition remains
recorded in0144; it is not relabeled successful. No additional full-funnel smoke or
three-parent real-model comparison was performed during this launch. The user
reviewed these results, removed the experimental branch and requested starting.

## Reproduce

Load the saved request through MCP `nise_plan`; inspect the resulting immutable
plan and start with its new id/digest. Use `job_status`/`job_wait` for the recorded
job. Resume this job through the broker after interruption; never edit its frozen
request, snapshot or outputs in place.

## Limits and what was not tested

Campaign is ongoing; no success rate, affinity improvement, throughput or final
hit claim. No app/DMG deployment or scientific code changes in this turn.

## Next

Continuation update: the original job was paused after 30 initial predictions for
the guidance comparisons in 0150–0151. The user chose to retain original guidance
and continue with all pending stage inputs submitted together. New job
`job-0f975ef0db89` uses the same output and scientific configuration, a separately
frozen continuation snapshot, and audited original checkpoints. See
[0152](0152-resume-biotin-with-stage-batches.md) for validation and launch evidence.
Resume the continuation job for this execution policy; the old job retains its
original singleton-submission snapshot.

Progress snapshot at 2026-09-17 20:47 UTC (16:47 EDT): broker running with no
reported error; 12/1000 initial structures complete, next prediction in progress.
On this M4 Max, these 12 resident structure requests averaged 51.64 s each (last
10: 52.30 s), all in one session with model-load count1. At that early mean,
remaining cycle00 work projects to 14.17 h; report roughly 14–15 h given the small
sample and variable lengths. This excludes all subsequent refinement and
optimization; no full-campaign ETA or controlled performance claim.
[Recorded timings](artifacts/0148-launch-biotin-without-noising/progress-20260917T2047.json).

On completion, inspect `results_overview`, then audit stage attrition, candidate
geometry, scored winners and model receipts. Diagnose broker errors and log tails
before changing any settings if the campaign stops.
