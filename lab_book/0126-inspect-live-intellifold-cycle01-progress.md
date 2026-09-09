---
entry: 0126
title: Inspect live IntelliFold cycle 01 progress
date: 2026-09-09
author: Codex
type: audit
status: complete
machine: Apple Silicon, 64 GB unified memory, macOS 26.6.1
tags: [performance, resident-workers, resume, observability]
---

## Context

The user asked whether the active IntelliFold cycle 01 was healthy because it
appeared to take indefinitely. This was an observation of an existing campaign,
not a new benchmark or a settings experiment.

## What was done

Queried the read MCP run catalog/status for `untitled_design`, then inspected
the durable desktop batch state, active resident request, worker log, output
timestamps, and frozen runner source. Read process activity, `vmmap -summary`,
`memory_pressure -Q`, swap usage, and GPU activity counters. No running process,
configuration, input, model, or output was changed.

## Results

At 18:52 EDT, `untitled_design_intellifold_full_6ed978fa` had written 48 of the
50 cycle-01 structures, each with full and parseable summary confidence files.
The latest structure was written at 18:49:51. Across 47 successive completion
intervals, mean was 253.95 seconds and median 247.66 seconds; the last ten averaged
252.42 seconds. These are observed wall-clock output intervals under the current
machine workload, not an isolated model benchmark or promises for other inputs.

The resident worker was alive (PID 25453), accumulating CPU time, using MPS with
model `v2`, and reported one model load. Its physical footprint was 14.0G with
a 14.1G peak. The memory-pressure query reported 60% free; system swap usage was
9,161.88 MB. Swap occupancy is cumulative and alone does not establish current
thrashing. A GPU counter sample showed nonzero utilization. No fatal error was
present in the active worker log.

The restarted request was submitted at 15:27:27. The worker logged **34 already
complete predictions being overridden**. Upstream emits this message only after
its `check_outputs` succeeds. The last of those recomputations completed about
8,542 seconds (2 h 22 min) after submission. This is real repeated work following
the prior interruption, not repeated model loading.

The frozen batch runner tests completion in each trajectory's cycle directory,
but copies batch predictions there only after the whole request returns. The
resident IntelliFold adapter sets `override=True`. Together, these cause an
interrupted unfinished batch to repeat predictions that exist in the batch output.
The generic heartbeat also hides per-design progress until the batch finishes.

Estimated remaining cycle-01 prediction time at inspection: approximately 5–10
minutes. Four further optimisation cycles are configured; if all 50 trajectories
continue at the observed pace, approximately 14–16 further hours for IntelliFold,
excluding the queued OpenFold engine. These are extrapolations, not measurements.

The observation metadata and completion timestamps are retained in
[the audit snapshot](artifacts/0126-live-intellifold-progress.json).

## Decision and rationale

Leave the progressing job alone, especially near the end of this batch. Another
interruption could replay it again. Future corrective work should make individual
batch predictions resumable with input/model provenance checks and expose their
completion count in the UI. Do not silently change inference settings to hide
the runtime cost.

## Reproduce

Use read-profile `runs_list(project="untitled_design")` and `run_status` for the
named run. Inspect `_cycle_wave/resident_sessions/session_20260909T152712_22473/`
and `_cycle_wave/cycle_01/batch_01/intellifold/inputs/predictions/` beneath it.
Count matching CIF/confidence sets and calculate differences between sorted CIF
modification times. Use `vmmap -summary 25453` only while it remains this worker;
PIDs must be rechecked before later inspections.

## Limits and what was not tested

No scientific quality assessment, new predictions, isolated speed benchmark,
resume fix, or UI change. File timestamps and counters are live observations.
The all-project MCP catalog hit a pre-existing symlink-path error; narrowing to
the requested project worked. Its run-status reader reported no PID for this
desktop batch, so actual liveness was verified against the durable job state and
OS process tree. The saved batch `exit_code: 130` remained from the prior pause
while the resumed worker was running; it was not evidence of a new crash.

## Next

Fix partial-batch resume and per-design progress reporting separately, without
mutating this active campaign's frozen runtime.
