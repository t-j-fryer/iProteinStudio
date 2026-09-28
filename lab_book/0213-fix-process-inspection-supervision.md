---
entry: 0213
title: Retain supervision through process inspection failures
date: 2026-09-28
author: Codex
type: bugfix
status: complete
machine: Apple M4 Max, 64 GB unified memory; model-free tests
tags: [mcp, queue, cancellation, ui, release]
---

## Context

The student archive in 0210 established that a three-second `ps` timeout escaped the broker and marked a job failed while its predictor continued. The user requested the fix plus app, MCP, GitHub and release updates, including the live resources panel from 0212.

## What was done

Process snapshots normalize timeout, command, malformed-output and OS failures to an explicit unavailable result expressed as an exception. Empty output never means no live processes. The broker retries within its supervision loop, retains the execution lease and ownership receipt, exposes a separate monitoring warning, and only finishes after a successful absence check. The first scan precedes reaping the direct child, preserving its PID identity. Worker readiness also retries before inference starts.

Stop remains pending during outages. Signals require a fresh verified snapshot; TERM is retried and its successful return starts the KILL grace period. Recovery retains discovered identities before signalling, never declares cleanup complete on inspection failure and reports an actionable error. No timeout was merely lengthened. Swift Job progress displays the monitoring warning independently from scientific stage and live resource telemetry.

Release metadata: 0.2.11/build57/MCP32. No scientific model, MSA, generation or scoring defaults changed. Older jobs retain their immutable worker code; updated supervision applies to new submissions.

## Results

- `swift build` passed; all 13 Swift tests passed, including five resource checks.
- Seven timeout fault-injection tests passed: startup, live real child, completion, Stop, lease retention, stale identities and interrupted cleanup.
- Three process-tree and eleven recovery tests passed, including real disposable children and an unrelated process retained alive.
- Fifteen engine-progress, twenty desktop-job and twenty-two MCP bridge tests passed.
- Both release shell contracts passed; diff whitespace checks passed.
- Rendered the full native Job progress view with inert job fixtures and real local resource counters; checked warning, telemetry and recovery controls. Evidence remains under ignored build/job-monitor-preview and build/student-debug-20260928.

A first sandboxed subprocess test could not inspect processes and was interrupted; tests then ran successfully with normal process access. No scientific process was stopped or launched by these tests.

## Decision and rationale

An unavailable process list is uncertainty, not proof of job failure or completion. Continue supervision while preserving exclusivity and verified ownership. Do not infer PID identity from cached data, release locks on transient inspection errors, or claim resource pressure caused the student's timeout without memory telemetry. Recovery is retryable and fails conservatively.

## Reproduce

`python3 -m unittest discover -s Tests -p 'test_monitoring_timeouts.py'`

Repeat for test_process_tree.py, test_job_recovery.py, test_engine_progress.py, test_desktop_jobs.py and test_mcp_bridge.py. Run `swift build`, `swift test`, and both release contract scripts. Real-child tests require OS process-list access.

## Limits and what was not tested

No forced memory exhaustion, live student-Mac test, GPU inference, performance comparison or biological validation. Persistent OS failure intentionally keeps supervision/Stop pending rather than guessing. Existing frozen jobs are not rewritten. The resource monitor is whole-Mac, optional GPU-driver telemetry and window-lifetime history, not per-job attribution or an always-on trace.

## Next

Publish and verify the clean release, update the installed app and shared MCP through normal runtime staging, and record deployment checks below.

## Release and deployment verification

Published v0.2.11-beta/build57/MCP32 from clean source commit 0056d55 through the standard trusted-beta release script. Update-feed commit d01ce9a was pushed to GitHub main. GitHub asset digests match local SHA256SUMS for both ZIP and DMG; the archive's Sparkle signature verifies with the existing release identity. The live appcast advertises 0.2.11/build57.

Replaced and reopened the existing `build/iProteinStudio.app`, preserving the previous bundle as `build/iProteinStudio-0.2.10-before-monitoring-update.app`. The installed signature verifies and all 170 packaged pipeline files match the clean release. Bundled and shared MCP doctors report32; shared broker, process-tree and recovery files match packaged hashes.

An existing Predict job completed naturally. A separate runtime benchmark was active during initial app staging, so the app correctly deferred workflow updates until its execution lease was released. That benchmark completed and normal app staging then installed MCP32. No scientific job was stopped, resumed or reconfigured for deployment.

Native computer-use inspection was unavailable (closed pipe); app process/version/signature and staged files were independently verified. The full Job progress UI was inspected in the inert native preview before packaging. Release artifacts are also available under canonical `build/unsigned-beta-0.2.11-57/`. The old student job retains its frozen code and requires cleanup/new submission to adopt the supervisor fix.
