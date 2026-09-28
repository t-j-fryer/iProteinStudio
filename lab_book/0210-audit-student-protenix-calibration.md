---
entry: 0210
title: Audit student Protenix calibration delay
date: 2026-09-28
author: Codex
type: audit
status: complete
machine: Student Apple M4 Pro, 24 GB unified memory (user supplied)
tags: [protenix, support, calibration, performance]
---

## Context

The user supplied a student project ZIP reporting problems. Diagnose saved evidence without executing archived code or changing the campaign.

## What was done

Read ZIP inventory, campaign budgets, immutable runtime snapshot, first calibration log and saved inputs; compared calibration scheduling and predictor capabilities with current source. Private evidence and report are under ignored `build/student-debug-20260928/` (`REPORT.md`, `predict.log`, `progress_events.csv`, archive SHA-256).

## Results

Historical log measurements only, not a new benchmark. Hardware specification unknown. Eight frameworks divide 100 trajectories as 13/13/13/13/12/12/12/12 with five optimisation cycles. Only the first calibration has begun in the archive. No generated structures or finished calibration metrics were present.

The archived pipeline is app 0.2.9; full Protenix v2 ran on MPS in FP32, requesting five samples, ten recycles and 200 diffusion steps. Loading completed in 28.3 seconds. The input reports 425 tokens and MSA depth 16,384. Cached MSA and target template loading succeeded.

The log covers 72 minutes 45 seconds. One Pairformer host call took 3,121.5 seconds before returning; genuine stage returns continue near the end, followed by an unfinished fifth MSA call. No traceback or OOM message was found. These host durations are not GPU completion measurements. Nested operation times cannot be summed.

## Decision and rationale

The missing results follow from unfinished startup calibration. Do not claim a crash, failed download, lost completed designs or confirmed swapping. Resource pressure is a hypothesis requiring the student's hardware/status and central job logs. Prepared framework directories are not failed campaigns.

Current v0.2.10 incremental result publication does not eliminate calibration; its calibration scheduling block matches the archived runner. Updating alone is not an established remedy, and immutable older runs retain their snapshot. Full Protenix v2 does not apply saved epitope fields as pocket steering; the target template was separately active.

## Reproduce

Inspect `/Users/thomasfryer/Downloads/iProteinStudio to debug.zip` with Python `zipfile`, without running its scripts. Compare archived `.studio_runtime/pipeline/nanohunter_run.sh` calibration block with `Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh`. See private audit report and parsed event CSV for evidence.

## Limits and what was not tested

No model rerun, live student process inspection, app rebuild or source modification. The archive lacks central job state/log, hardware details, memory pressure, swap and GPU telemetry. Present job state and full-campaign runtime cannot be inferred. No new biological design recommendations were made.

## Next

Obtain Job progress → Copy support report and the central job directory referenced by archived studio_job.json. If still running, collect Activity Monitor memory pressure and Swap Used. Diagnose the resource issue before recommending altered inference defaults.

## Follow-up finding — supervisor timeout confirmed

The student reports Apple M4 Pro with 24 GB unified memory. The central job archive establishes a separate supervisor failure that was not visible in the first archive. At 20:35:27 UTC, state.json records status=failed because subprocess.TimeoutExpired escaped ProcessTree.refresh(): `/bin/ps -axo pid=,ppid=,pgid=,stat=,lstart=` exceeded its three-second timeout. This was a monitoring subprocess failure, not a Protenix inference exception.

The predictor continued afterward: genuine stage returns are recorded through 21:03:26 UTC and heartbeats through 21:07:50 UTC, over 32 minutes after the manager declared failure. The supervisor abandoned its normal monitoring loop while inference was still alive. This explains inconsistent failed status alongside continued GPU work. The log ends with a missing predict.log diagnostic and a generic calibration prediction failure; there is no evidence establishing why the path disappeared or a model-level traceback explaining final termination.

The archived process_tree.py is byte-identical to current source. Its unhandled monitoring timeout is therefore not fixed by v0.2.10. A robust correction must retry/report transient inspection failures, retain ownership records and supervision, distinguish an unavailable process snapshot from no live processes, and avoid signalling stale/unverified PIDs. Cancellation/recovery and lease handling must be tested together. Merely lengthening the timeout or treating errors as an empty process list is insufficient.

Full Protenix v2 on 425 tokens with a reported 16,384-row MSA and FP32 may impose substantial resource pressure on a 24 GB machine. Memory pressure/swapping remains unconfirmed; no memory or swap samples were supplied. A 7.5-minute wall-clock gap advances the progress elapsed counter by only 30 seconds, consistent with sleep or a clock discontinuity; total wall time must not be treated as uninterrupted GPU computation.

No software or run settings were changed during this follow-up. If the old job is still consuming resources, the existing Job progress → Check & clean up action is the relevant ownership-aware recovery path; it too relies on process inspection, so it may report an error under continuing system stalls. Saved outputs should be retained.
