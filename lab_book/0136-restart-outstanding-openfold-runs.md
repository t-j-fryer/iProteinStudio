---
entry: 0136
title: Restart the ten outstanding OpenFold campaigns through the broker
date: 2026-09-16
author: GPT-6
type: implementation
status: complete
machine: local Apple Silicon Mac; no performance measurement
tags: [openfold3, queue, recovery]
---

## Context

Following [[0133-fix-openfold-scheduler-and-audit-queue]], the user explicitly
requested starting the outstanding OpenFold runs. The three failed parent batches
had ten OpenFold campaigns with no predictions: two minibinder campaigns and
eight nanobody scaffold campaigns, totaling 150 trajectories and 750 optimization
cycles, plus 150 cycle-00 starts.

## What was done

Called the iterative workflow guide and engine detection. Verified the original
three immutable plan digests and their script/input provenance, the original
scheduler failure logs, the empty queue, and the absence of scientific outputs
in each of the ten unfinished campaigns.

Backed up each original `studio_run.json` and any `studio_job.json` under the
campaign's `.studio_recovery/openfold_scheduler_v1/`. Changed only the recorded
scheduler from `resident` to `run` and removed `--wave-batch-size all`. Preserved
output paths, frozen pipeline snapshots, sequence designers, seeds, trajectories,
cycles, MSA requirement, and all other scientific arguments. Original immutable
plans and all completed engine results remain unchanged.

Executed each campaign's frozen shell runner with `--check-config`; all ten
passed. Created ten new immutable plans using the shipped native `desktop_plan`
adapter. Reviewed every normalized command and its 51 or 55 provenance records;
submitted each returned plan ID and SHA-256 to `broker.start_job`. Wrote each
new broker reference to its campaign's `studio_job.json` for native app discovery.
The broker's immutable-plan recheck and shared exclusive execution lock remain
in force; models were not started directly.

Saved the reproducible operational helper, preflight logs, original-plan links,
new plan IDs/digests, new job IDs and observed status under
[artifacts/0136-restart-openfold](artifacts/0136-restart-openfold/started.json).

## Results

No measurements — recovery/start operation only, not a benchmark.

- Ten real frozen-runner configuration preflights passed.
- Ten new broker jobs submitted, representing 750 outstanding optimized designs.
- Observed one running (`job-c2773eab4479`) and nine queued.
- The running helix-strength-0 minibinder campaign passed the former failure point,
  reused the exact cached target MSA (1,231 records), confirmed the OpenFold
  checkpoint, and entered its normal single-prediction calibration.
- Completed 4,500 optimized designs from the previous audit were not resubmitted.

The first helper start attempt rejected its own list-shaped JSON audit file
before submitting any job; corrected that reader and retried. A sandboxed status
attempt lacked process visibility and tried to refresh state as interrupted;
filesystem protection prevented that write. The subsequent broker status check
outside the sandbox confirmed the actual one-running/nine-queued state.

## Decision and rationale

Create fresh native plans from the corrected manifests so historic immutable
plans stay auditable. Preserve the existing campaign destinations and snapshots,
rather than rebuilding scientific settings from today's UI or copying changed
runtime science. This is the user's authorized continuation of existing campaigns,
not a new target/settings experiment. The shared lock serializes GPU ownership.

## Reproduce

From the canonical repository, inspect the recorded plan and job IDs:

```bash
cat lab_book/artifacts/0136-restart-openfold/prepared.json
cat lab_book/artifacts/0136-restart-openfold/started.json
python3 lab_book/artifacts/0136-restart-openfold/recover.py status
```

Status checks need process visibility outside a restrictive sandbox because the
broker reconciles vanished workers. The `prepare` and `start` actions are retained
for audit; do not rerun preparation over active or completed campaigns. Broker
submission is idempotent for an existing plan ID.

## Limits and what was not tested

Observed startup and queue ownership, not completion of the 750 optimization
cycles. No performance estimate, new full inference acceptance, experimental
validation, app relaunch, commit or release. The codebase's unrelated existing
changes were preserved. Historic failed parent batches retain their failed
records; the ten replacement jobs own the outstanding child campaigns.

## Next

Allow Studio's durable queue to finish. Poll the saved job IDs and inspect
`error`/`pipeline_log_tail` before changing settings if a job fails. Review finished
run/cycle artifacts via `results_overview` before interpreting scores.

## Progress check — 2026-09-17 03:45 UTC

One running, nine queued, no failed recovery jobs. The helix-strength-0
minibinder campaign has 33/50 fully finished trajectories, 165/250 saved
optimized structure files and 33 cycle-00 starts; trajectory 34 is in progress.
That is 165/750 optimized structures across the entire recovery queue.
The pipeline log was freshly updated and the MCP result overview exposes the
per-run cycle hierarchy. No settings changed or jobs restarted.
See [progress snapshot](artifacts/0136-restart-openfold/progress-20260917.json).

## Progress check — 2026-09-17 15:18 UTC

Observed 719/750 saved optimized structures; broker states: {'completed': 8, 'running': 1, 'queued': 1}.
Both minibinder campaigns completed. No failed recovery jobs.
See [queue/output snapshot](artifacts/0136-restart-openfold/progress-20260917T151853Z.json).
No settings changed or jobs restarted.

## Progress check — 2026-09-17 16:01 UTC

Observed 750/750 optimized structures and 150 cycle-00 starts; broker states: {'completed': 10}.
Completed campaigns were checked for exact summary run/cycle cardinality and existence of every summary-referenced structure; individual outcomes are in the snapshot.
See [queue/output snapshot](artifacts/0136-restart-openfold/progress-20260917T160114Z.json).
No settings changed or jobs restarted.

## Final user summary — 2026-09-17

Re-read all 70 campaign manifests and summary CSVs across the three original
batches. All are completed, with 1,750 optimized outputs and 350 starts in each
batch. Recorded the shared seven-engine setup, minibinder settings, eight-scaffold
allocation, recovery history and distinction between cycle outputs and confirmed
binders in [the final summary](artifacts/0136-restart-openfold/FINAL_SUMMARY.md).
Total: 5,250 optimized run/cycle records plus 1,050 starts; 1,050 final-cycle
records. No additional inference or ranking was performed.
