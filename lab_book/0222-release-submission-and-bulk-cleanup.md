---
entry: 0222
title: Release shared submission progress and safe bulk cleanup
date: 2026-09-29
author: Codex
type: bugfix
status: in-progress
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

-25 desktop job tests pass, including actual inert worker execution for all
 four main workflows, scaffold batches, target preparation and calibration,
 registration/validation error receipts, cancellation, resume and provenance.
-14 recovery tests pass, including global live/queued-worker exclusion, damaged
 record continuation, MCP scopes, PID reuse and a real disposable orphan stopped
 while an unrelated process survives.
-22 MCP integration tests,6 request-reuse tests,13 Swift tests and all native
 Swift controller/result harnesses pass. Both release contracts pass.
-`swift build` passes. Final monitoring-timeout checks and package verification
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
