---
entry: 0128
title: Stop the IntelliFold campaign after cycle 01 and relaunch build 35
date: 2026-09-09
author: GPT-6
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [intellifold, resume, desktop]
---

## Context

After [Entry 0127](0127-checkpoint-resident-intellifold-predictions.md), the user
asked to stop the current IntelliFold campaign once cycle 01 finished and update
their running Studio app. Cycle 01 had already completed when inspected; the
campaign was executing cycle 02. Reported this before stopping it immediately.

## What was done

Inspected the read-profile run status, durable desktop job state, cycle response
receipt, and process tree. Called the job's frozen `studioctl.py cancel` through
the existing broker for `job-4d54e18d450b`; no direct worker kill or lease bypass.
Waited for terminal cancellation and confirmed the supervisor, shell and resident
worker exited. Verified that all cycle 01 structures and summaries remain present.

The running app was the development-path bundle at
`/Users/thomasfryer/iProteinStudio/build/iProteinStudio.app`, not an Applications
installation. Its on-disk bundle already contained the verified 0.2.0 build 35
from Entry 0127, but the running process predated that update. Verified the bundle
signature and version, quit the old app through its normal Apple-event quit
handler, confirmed exit, and reopened that same updated bundle. The campaign was
not resumed and its frozen runtime was not modified.

## Results

- Cycle 01 batch response: success, 50 jobs, completed at
  **2026-09-09 23:01:25 UTC (19:01:25 EDT)**.
- After stopping: 50 nonempty materialized cycle 01 CIF structures and 50
  confidence summaries, with their links resolving to retained files.
- One cycle 02 CIF was present in the partial batch and was retained. Its presence
  alone is not a claim that the prediction or cycle is complete.
- Desktop job reached `cancelled`, exit code 130, at
  **2026-09-09 23:13:01 UTC (19:13:01 EDT)**, with message
  `Stopped. Completed checkpoints were kept.` and no error.
- Old app PID 33674 exited. The reopened bundle identifies itself as version
  0.2.0, build 35. No new model inference was requested.

No performance measurements or scientific assessment were made.

## Decision and rationale

The requested boundary had already passed. Stop immediately and retain partial
cycle 02 work instead of allowing another full cycle. Use the broker so it can
stop/reap its child processes and release the execution lease. Relaunch the
updated bundle the user actually uses; no unnecessary second installation or
replacement of the campaign's immutable runtime.

## Reproduce

Read the durable state at
`~/.iproteinstudio/agent/jobs/job-4d54e18d450b/state.json`, and the run's
`_cycle_wave/resident_sessions/session_20260909T152712_22473/responses/request_cycle_01_batch_01.json`.
The run is
`~/.iproteinstudio/projects/untitled_design/untitled_design_intellifold_full_6ed978fa`.
Check retained `run_*/cycle_01/pred_min/` links and the app's `Contents/Info.plist`.

## Limits and what was not tested

No campaign resume, runtime migration, new predictions or UI automation tests.
The existing campaign retains its older runtime and does not acquire build 35's
per-prediction resume fix merely because the app was relaunched. It was not
possible to stop exactly at the boundary retroactively; cycle 02 had already
started before this request was handled. No binary GitHub release was published.

## Next

Leave the campaign stopped until the user requests further work.
