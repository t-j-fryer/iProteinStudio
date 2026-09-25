---
entry: 0189
title: Add a job progress viewer and safe recovery
date: 2026-09-25
author: Codex
type: implementation
status: complete
machine: Local development Mac; synthetic jobs and UI preview, no engine inference
tags: [ui, jobs, progress, recovery, support]
---

## Context

Following [0187](0187-inspect-student-run-archive.md) and
[0188](0188-add-engine-progress-logging.md), the user requested an easy in-app
progress viewer and a way to clean up stalled jobs without damaging other work.

## What was done

- Added `JobProgressView` to the queue and Activity/history. It polls a bounded
  job-log endpoint every two seconds, presents the latest engine event, readable
  events/raw output/worker-log tabs, selectable text, follow-latest scrolling,
  privacy-preserving support copy and a separate explicit raw-log copy.
- Added a read-only recovery check and confirmation-based cleanup. Live compatible
  workers receive normal cancellation. After a worker crash, only processes whose
  recorded PID/start identity still matches are signalled. Current descendants
  of verified live parents can be included. No name, group-number or lock-holder
  guessing. TERM has a three-second grace, then verified survivors receive KILL;
  stubborn survivors remain stopping with restart guidance.
- Worker supervision now persists observed identities as `processes.json`, and
  records the worker's birth identity in `worker_ready.json`. Resume refuses to
  start a second worker over recorded surviving processes.
- Recovery holds the registry lock against concurrent Resume/submission, rechecks
  identity immediately before signals, preserves cancellation intent separately,
  retains all results/runtime files and never unlinks the execution lock.
- Prepared campaign manifests default to Prepared. History distinguishes Prepared,
  Waiting, Running and Stopping; not-yet-started scaffold children no longer appear
  to be executing. Queued/terminal job records remain authoritative.
- CLI endpoints `job-log`, `job-recovery-check`, `job-cleanup` support the native
  viewer; no new externally exposed MCP tools/profiles were added.

## Results

No scientific runtime or throughput measurements were made.

| Verification | Outcome |
| --- | --- |
| Job recovery tests | 11 passed: PID reuse, unrelated process exclusion, legacy worker refusal, readiness race, normal Stop, stale state repair, files/lock retention, real child termination, Resume exclusion, bounded CLI output and invalid ID rejection |
| Existing desktop queue/cancellation suite | 19 passed |
| Added worker-crash recovery integration case | Passed: killed only the temporary fixture worker, cleaned its separate-group TERM-resistant descendants holding the inherited lock, retained its folder, next queued fixture completed |
| Engine progress regression tests | 14 passed after recovery integration |
| `swift test` | 8 XCTest cases passed, including two new event-parser/heartbeat semantics cases |
| Native Swift contract harnesses | All 8 harnesses passed; added Prepared-state assertions for independent and scaffold campaign manifests |
| `swift build` | Passed |
| Visual inspection | Production viewer rendered in an isolated native window with inert fixture models; layout checked and long log lines wrap without hiding controls |

Preview: [viewer.png](artifacts/0189-job-progress-recovery/viewer.png). The preview
is synthetic, not a screenshot of the student's or user's real job. The preview
harness does not load Studio's application startup or broker. Its process exits
after capturing only its own window.

## Decision and rationale

Prefer job-specific recovery with retained process identity over deleting lock
files, clearing shared scratch directories or killing processes by engine name.
Never declare a heartbeat equivalent to GPU progress, and never turn elapsed
silence into automatic cancellation. Preserve the older job's scientific/runtime
identity; new submissions are required to adopt updated frozen worker code.

Older unidentifiable leftovers cannot be safely reclaimed automatically. The
viewer supplies plain restart/new-submission guidance rather than a terminal
command or an unsafe force-clean action. Cleanup is not a disk-space purge.

## Reproduce

```bash
python3 Tests/test_job_recovery.py
python3 Tests/test_desktop_jobs.py
python3 Tests/test_engine_progress.py
python3 Tests/run_swift_contracts.py
swift test
swift build
```

Recovery/process tests require access to `/bin/ps` and use temporary job registries
and their own inert subprocesses only. UI rendering uses
`Tests/JobProgressPreviewHarness.swift` with the production view and an isolated
StudioCore build; it deliberately substitutes fixture view models for all broker
operations.

## Limits and what was not tested

No application deployment, GitHub publication, student-Mac execution, real job
cleanup, full engine inference, cross-chip/OS testing or live application navigation.
The UI was rendered with fixtures, not used to stop an actual campaign. Existing
active jobs and their installed code were not changed. The student's original
prediction delay remains undiagnosed.

No claim of recovering deliberately evasive descendants that escaped observation,
older processes without identity receipts, or kernel-uninterruptible processes.
PID/start-time checks narrow normal PID-reuse races but are not an OS process
containment mechanism. Uninstrumented preparation retains existing logs. No job
deletion, model-cache purge, GPU-utilization estimate or fabricated percentage.

## Next

Package the viewer, recovery and engine observer together in a subsequent app
release; perform fresh-Mac and full-engine acceptance separately. Users need a new
submission to acquire the new worker identity receipts and instrumentation.
