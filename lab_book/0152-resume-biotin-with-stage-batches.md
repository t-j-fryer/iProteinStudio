---
entry: 0152
title: Continue original biotin campaign with stage-directory submissions
date: 2026-09-17
author: GPT-6 Codex
type: implementation
status: complete
machine: Apple M4 Max, 64 GB unified memory
tags: [nise, boltz, resume, resident]
---

## Context

After 0151 the user chose the original physical+FK approach, requested all inputs
together and continuation of the paused 1000-start campaign. Original job
`job-002ee4e5c61e` was cancelled with 30 completed cycle00 units.

## What was done

Added opt-in `BatchBackend` and native-writer completion markers. One directory
request per pending folding stage; selective affinity retains its exact selection
batches. Each prediction is copied to the existing per-input layout and audited
before its durable receipt is committed. Resume also recovers native writer
markers when interruption occurs before controller commit. Progress resets the
30-minute inactivity deadline, allowing long active requests.

A new immutable continuation plan points to the same output and unchanged
scientific config, with a separate code snapshot. Original snapshot, plan,
30 checkpoints, structures and atom map remain intact. Default app scheduling
is unchanged. No partial noising, adaptive sampling or early exposure killing.

## Results

The real-model smoke `job-3a3397d12144` completed successfully, exit 0, at
2026-09-17 23:44:26 UTC. It submitted two structure inputs together, interrupted
after the first native writer finished but before controller commit, recovered
that output, and submitted only the remaining input. Both saved structures then
passed through a single two-input affinity request. Repeating fold+affinity made
no further requests and left all four operation receipts unchanged. Exactly one
completed native structure per input was recorded; the interrupted partial second
prediction was discarded. Structure/affinity model-load counts were 1 then 2 in
the resumed worker. Explicit MPS used; two documented SVD fallback warnings, no
other fallback. Intentional worker termination emitted a semaphore cleanup warning.

Independent hash/checkpoint audit passed. `results_overview` returned the NISE
hierarchy with zero candidate rows because this is a transport smoke, not a full
search; no hits or biological quality are inferred. Full frozen plan, model/source
fingerprints and status are in `Validation/output/nise_stage_batch_resume_v1/smoke2`.
[Independent audit](artifacts/0152-stage-batch-resume/smoke-audit.json).

The NISE Python suite passed 45 tests; after adding the entry-point regression,
both checkpoint-worker tests passed. `swift build` passed. A sandbox-only build
attempt failed accessing compiler caches; normal cache access resolved it.
Managed installation detection passed before planning.

Failures retained: initial smoke preflight refused eight trajectories with only
two starts; bounded smoke corrected to two trajectories. First launched smoke
`job-acbad6104a92` failed before model loading because the wrapper passed a string
to the shared service's Path-based entry point. Fixed to `Path(config)`, added a
regression test, and used a fresh immutable snapshot/plan for the successful run.
No failed raw outputs were edited.

## Decision and rationale

Plain `job_resume` would execute the old singleton-submission code. Record an
explicit continuation instead of changing its immutable snapshot. Keep physical
and FK guidance and stage-specific pocket controls exactly as before. The source
science modules were checked byte-for-byte against the original snapshot before
preparing the continuation; all original operation receipts and their artifacts
were verified twice before launch.

Continuation plan: `plan-0f975ef0db89cf1a`, SHA256
`0f975ef0db89cf1a8b7b41a8c3833a7ea1757c1afabbd7c0ce8b747275649b68`.
Same output: `test2/nise_runs/nise-7345aaf6c30d1a9e` in managed projects.
[Plan and launch evidence](artifacts/0152-stage-batch-resume/continuation/).

## Reproduce

`Validation/experiments/nise_stage_batch_resume_v1/prepare.py` creates smoke and
continuation plans. Launch only through MCP `job_start` with their saved digest.
The experiment README and manifest declare the procedure; `audit.py` independently
checks smoke receipts, request cardinalities, model loads and fallback logs.

## Limits and what was not tested

No completed 1000-start campaign or long memory soak yet. No new throughput
measurement or speedup claimed. Batching changes the future request RNG stream and
native preprocessing order; membership and preprocessed assets are recorded.
Existing completed samples are unchanged. Mixed per-input seed overrides are
rejected in this opt-in route; partial noising is disabled in this campaign.
No new app/DMG installation or GitHub publication was requested/performed here.

## Next

Launch verification at 2026-09-17 23:47:14 UTC: `job-0f975ef0db89` is running.
One request contains all 970 pending initial inputs; resident worker PID 97786
uses MPS and model-load count 1. First new prediction `L155` completed and its
receipt/artifacts verify, giving 31/1000 completed initial structures. Native
directory processing order differs from numeric lineage order. All 30 original
checkpoints and their artifacts still verify unchanged. The native app's
`studio_job.json` now points to this continuation; its previous association is
archived in the lab artifacts.
[Startup audit](artifacts/0152-stage-batch-resume/continuation/startup-audit.json).

Implementation/validation/launch are complete; the scientific campaign remains
ongoing. Review the continuation job through the broker, and resume that job if
interrupted. Audit full campaign outcomes before interpreting any binding hits.

## Submission status follow-up — 2026-09-18 01:18 UTC

Read-only inspection for the user's submission question: the broker reports
`job-0f975ef0db89` running. The current session has one structure request,
`bb65105ae3284d6895e864f4488377f2`, declaring 970 jobs; its input directory
contains 970 YAML files, each with an X-containing sequence. The 30 previous
completed starts were reused. At 01:18:19 UTC, cycle00 contained 153 per-input
completion receipts (30 previous plus 123 new), leaving 847 initial structures.
The worker log independently showed 123/970 and active per-input output writes.
No later cycle directory existed yet. This is one stage-directory submission
processed incrementally by the resident predictor; later-stage sequence generation
depends on these initial structures.

Reproduce with the managed `mcp/studioctl.py job-status job-0f975ef0db89`, then
count cycle00 input YAMLs and `L*/completed.json` and inspect the current session's
request and worker log. No settings or running-job changes, benchmark, new tests,
or full artifact hash audit were performed in this status follow-up. Completion
counts are a point-in-time snapshot, not final campaign outcomes.

## Progress on 2026-09-18

At 16:07 UTC, broker reports running with no error. All 1000 initial
structures are complete; 422 pass the saved initial atom geometry checks.
Cycle01 generated three sequences per surviving lineage: 1266 total;
312 structure checkpoints complete, no affinity checkpoints yet. The most recent
100 structure+writer durations average 44.51 s on the M4 Max.
At that observed rate, remaining cycle01 folding takes approximately
11.8 h, excluding affinity and every later stage. This is an
extrapolation, not a controlled benchmark or full-campaign ETA. The same resident
session has advanced from initial generation into refinement. Results overview
was inspected first; no finalized optimization trajectory rows exist yet.
[Progress evidence](artifacts/0152-stage-batch-resume/progress-20260918.json).
