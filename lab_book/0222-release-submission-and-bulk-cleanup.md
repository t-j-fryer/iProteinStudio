---
entry: 0222
title: Release shared submission progress and safe bulk cleanup
date: 2026-09-29
author: Codex
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [queue, submission, recovery, mcp, release]
---

## Context

Following [0221](0221-fix-scaffold-batch-submission.md), the user requested
publication, submission coverage across all workflows, and one button to clean
up abandoned jobs across workspaces. The student's current submission logs are
still unavailable: the identified defects are reproduced code defects, not a
confirmed complete diagnosis of that Mac.

## What was done

Included the parent-only scaffold batch plan and Prepared history correction.
All native submissions now retain studio_submission_status.json with validation,
runtime preservation/verification, registration and failure stages. The shared
ManagedJobSession reads new status updates while awaiting registration. Protein
Hunter, NISE, Predict, RFdiffusion3, target preparation and calibration display
these updates. Preparation remains outside the registry lock; immutable request
reuse, input hashes, exact runtime bindings and job execution locks remain.

Jobs adds Clean up abandoned jobs. The shared recovery implementation rechecks
each job under registry.lock, skips live/queued supervisors (also a supervisor
that resumed since the bulk scan began), and stops only birth-identity-verified
orphan processes. Unknown legacy workers are kept. Stale active states can be
cleared; history, inputs, results, runtimes and lock files are not deleted.
Per-job errors are accumulated while other jobs continue. MCP35 jobs_cleanup
uses this implementation with run/admin mutation scopes; read cannot invoke it.

Release metadata is0.2.14/build60/MCP35. No scientific defaults changed.

## Results

- 25 desktop job tests pass, including actual inert worker execution for all
 four main workflows, scaffold batches, target preparation and calibration,
 registration/validation error receipts, cancellation, resume and provenance.
- 14 recovery tests pass, including global live/queued-worker exclusion, damaged
 record continuation, MCP scopes, PID reuse and a real disposable orphan stopped
 while an unrelated process survives.
- 22 MCP integration tests,6 request-reuse tests,13 Swift tests and all native
 Swift controller/result harnesses pass. Both release contracts pass.
- `swift build` passes. Final monitoring-timeout checks and package verification
 are recorded with deployment below.

The first MCP suite ran inside a sandbox that disallowed process inspection and
localhost sockets; it failed7 tests and errored1. The identical suite passed all22
with normal OS access. No scientific inference was involved. Tests use temporary
registries and inert adapters, not the active biotin campaign.

## Decision and rationale

One validated plan owns a scaffold batch. Preparation progress is descriptive,
not a fabricated percentage or proof of inference. No arbitrary timeout/retry
was added that could accidentally create another job. Bulk cleanup is distinct
from Cancel all: it cannot request stopping a live supervisor. Retain individual
recovery for explicit cancellation and diagnosis of unverified older workers.

## Reproduce

Run Tests/test_desktop_jobs.py, Tests/test_job_recovery.py,
Tests/test_mcp_bridge.py, Tests/test_plan_reuse.py,
Tests/test_monitoring_timeouts.py and Tests/run_swift_contracts.py;
run swift test, swift build and both release shell contract tests.
Logs are retained under ignored build/0222-*.log.

## Limits and what was not tested

No fresh physical Mac, student-machine reproduction, GPU inference matrix,
throughput benchmark or scientific accuracy changes. Existing frozen jobs keep
their original worker code. Large model preservation can still take time; status
reports stages rather than progress per byte. Unidentifiable legacy processes
are deliberately not killed by bulk cleanup.

## Next

Publish from a clean release checkout, verify signed update archives and feed,
install the app and shared bridge, and record exact deployment results here.


## Deployment verification

Published v0.2.14-beta from clean source771befb; signed-feed commitad2a662.
GitHub asset digests match local SHA256 for the DMG, ZIP, checksum list and build
provenance. The live main appcast matches the generated feed and advertises
build60; Sparkle's ZIP signature verifies with the existing project identity.
DMG SHA256:63761add42da86aa1a44cbe2b5966fda42913869305218083c8d997716998e30.
ZIP SHA256:9ec9f2b5929d43c78fda4ba610f17e3e619db10c9bd8abacd5699b2728c26fca.
Seven monitoring-timeout tests and a final14-test recovery rerun passed.

The active biotin job813a5a13d54c held the shared execution lease. Requested its
normal broker cancellation; it reached cancelled with saved checkpoints kept.
Quit the old app after closing its Engines sheet, retained it as
build/iProteinStudio-0.2.13-before-submission-update.app, and installed/reopened
the published app at the existing build/iProteinStudio.app location. Normal app
staging installed MCP35. Doctor and engine detection pass. Every packaged MCP
file matches the shared installation; the app version/build and signature pass.

Resumed the original job813a5a13d54c with the unchanged immutable plan and
configuration hashes. Supervisor4244 reports running without error or monitoring
warning. Fresh logs replay saved work and reach Phase1 with eight independent
trajectories; no scientific parameters were changed. Existing MCP client sessions
must reconnect to load the new tool catalogue. No production bulk cleanup was
run as a test.

Native automation verified the updated window opens and observes one active job.
It could not reliably open/inspect the Jobs popover (AX clicks returned unchanged
state and coordinate attempts returned noWindowsAvailable). Manual visual
acceptance of that popover remains untested; the view compiles in the packaged
app and its backend behavior is covered by the executed recovery tests.
Deployment evidence remains under ignored build/0222-deployment and
build/0222-publish.log. Artifacts remain in the isolated canonical worktree's
build/unsigned-beta-0.2.14-60 directory.
