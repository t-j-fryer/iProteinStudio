---
entry: 0187
title: Inspect student run archive
date: 2026-09-25
author: Codex
type: audit
status: complete
machine: Student Mac hardware and macOS unknown; read-only local archive inspection
tags: [support, jobs, cancellation, protenix, provenance]
---

## Context

The user supplied `All_folders.zip` to check the reported stalled calibration
and repeated submissions. This follows [0186](0186-repair-submission-retries-and-cancellation.md).
The archive is evidence, not executable input. No supplied scripts were run.

## What was done

Read ZIP entries directly, checked CRC integrity, inventoried job pointers,
campaign metadata, logs and structures, and compared every saved broker, planner
and pipeline runner with the Git tag `v0.2.3-beta`. Recorded a sequence-free
inventory in `artifacts/0187-student-archive/audit.json`; reproduction script is
alongside it. Original archive and all active jobs remain unchanged.

## Results

This is a forensic audit, not a performance benchmark. Times below are recorded
events from the student's logs and metadata, not measured inference throughput.

- Two batch submissions, each with eight scaffold campaign folders. One unique
  job ID: `job-696abd42540f`, matching the support report. Its pointer occurs in
  the first batch and first campaign. The second batch has no job pointer.
- All sixteen saved copies of `broker.py`, `plans.py` and `nanohunter_run.sh`
  match release 0.2.3 byte for byte; saved MCP version is 24.
- Only the first campaign contains runtime output: target MSA preparation and
  calibration inputs/logs. No predicted structures, completed calibration or
  optimization cycle outputs are present. All archived CIFs are input templates.
- Target MSA search completed. Protenix selected MPS, finished loading its
  checkpoint, and featurized the input with the supplied target template.
- Log timestamps: MSA preparation begins 10:08:25; predictor begins 10:08:36;
  checkpoint loaded 10:09:33; final timestamped line 10:09:37 reports input
  dimensions immediately before the prediction call in the inspected installed
  runner. There is no success message, exception traceback, explicit OOM or
  Metal error. The last text is a leaked-semaphore warning during shutdown.
- ZIP modification time for that log is 10:30:10 (ZIP timestamps have no timezone).
  The manifest records stopped at 14:30:14 UTC, consistent with the previously
  reported stop around 14:30 UTC and logs using local UTC−4. The log's final
  timestamp therefore precedes the reported stop by about 20 minutes; this is
  an observation gap, not proof that computation made no progress.
- Fifteen manifests say `running`, with updated time equal to creation time.
  Source inspection explains this: `StudioRunManifest.state` defaults to
  `.running`, and batch creation writes all child manifests before submission.
  These labels do not establish fifteen running processes or queued broker jobs.
- No agent plan/registry/job-state records, lock ownership records, process
  samples, memory telemetry, or worker/pipeline logs are included.

## Decision and rationale

The archive confirms which job and released code were involved and locates the
last observed progress at prediction. It does **not** establish a root cause for
the original calibration delay. Slow computation, memory pressure and a backend
hang remain distinguishable only with additional runtime evidence. The semaphore
warning is consistent with interrupted multiprocessing cleanup; it does not prove
the semaphore caused the stall or that a descendant retained the execution lock.

The two 0186 bugs were independently reproduced and fixed in 0.2.4, but this ZIP
does not prove either was triggered here. Sixteen campaign-owned code snapshots
are expected for sixteen prepared campaigns; they are not the eighteen random
agent runtime views described in the earlier support account.

Treat the remaining folders as prepared/unstarted, not confirmed queued work.
Keep scientific settings unchanged. A proper follow-up would add stage/progress
and resource diagnostics, and distinguish prepared/queued/running native status;
do not call the original prediction hang fixed merely because 0.2.4 fixes retry
identity and cancellation cleanup.

## Reproduce

```bash
python3 lab_book/artifacts/0187-student-archive/audit.py \
  /Users/thomasfryer/Downloads/All_folders.zip \
  > lab_book/artifacts/0187-student-archive/audit.json
```

The script reads archived metadata and compares hashes; it does not extract,
execute, modify or publish the supplied files.

## Limits and what was not tested

No prediction rerun, student-machine inspection, process/lock diagnosis, memory
measurement, app build or app changes. The local installed Protenix runner was
used only to interpret the final log location, not to establish an exact hash
match to the student's engine installation. No proof of hardware compatibility,
normal expected run duration, actual post-featurization MSA depth or the original
termination signal. The archive cannot establish completeness of other jobs.

## Next

Use broker job state plus process/resource evidence for any recurrent stall.
Fix misleading native prepared-state labels separately with lifecycle tests.

## Follow-up: template compatibility

The supplied target template was explicitly requested in `guide` mode. The saved
mapping receipt aligns 300 of 304 target residues (98.684% coverage) with 100%
identity over aligned residues. Calibration JSON attaches the template to target
chain B and an explicit empty template list to binder chain A. The log confirms
one target template and zero binder templates were found, then reaches the final
input-dimension line. This establishes successful template ingestion, not a
completed template-conditioned forward pass.

The recorded predictor is Protenix v2; the sequence designer is AntiFold.
Studio's adapter explicitly permits user templates for Protenix v2 and limits
this route to guide mode. Upstream's
[inference demo](https://github.com/bytedance/Protenix/blob/main/inference_demo.sh)
also explicitly shows `protenix-v2` with `--use_template true` (checked 2026-09-25).
Thus selecting Protenix v2 with a target template is supported; the supplied
evidence does not show a template-format or sequence-mapping failure. It cannot
exclude a template-related issue later in model execution. No rerun or changes.

## Follow-up: silent prediction interval

Read-only inspection of the local installed runner shows an INFO message before
`runner.predict(data)` and a success message after prediction and output writing.
`predict()` transfers inputs to the device and calls the model; the inspected
recycling loop has no per-recycle progress logging. The Studio adapter inherits
stdout/stderr for ordinary Protenix v2 (it does not capture these until exit);
the shell redirects them into `predict.log`. Thus sparse engine progress reporting
explains why a long forward pass can be silent. This is a user-feedback and
diagnostic gap, not proof of a deadlock, and changing output buffering alone would
not create the missing milestones. Fine-grained stage reporting should distinguish
host progress from completed asynchronous GPU work and must not claim that a
process heartbeat proves computation is advancing. No instrumentation implemented
or runtime qualification performed in this follow-up.
