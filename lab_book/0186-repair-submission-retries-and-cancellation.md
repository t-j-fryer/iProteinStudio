---
entry: 0186
title: Repair repeated submission identity and escaped-child cancellation
date: 2026-09-25
author: Codex
type: bugfix
status: in-progress
machine: Apple Silicon development Mac; inert software fixtures only
tags: [queue, cancellation, runtime, distribution]
---

## Context

A student using the latest published release (0.2.3, build 46) reported a stopped
Protenix calibration, repeated plans without jobs, and possible inherited-lock
holders. The user requested diagnosis by source inspection and reasoning, without
waiting for more information from the student. No access to that Mac or its logs
was available. The report's suggested causes were treated as hypotheses.

## What was done

Confirmed `_persist` included a randomly named prepared runtime view in its plan
digest. Two identical saved requests produced two plans and two views. Changed
preparation to use an identity derived from normalized settings, recorded inputs,
code and selected runtimes. An atomic reference and per-request file lock reuse
finished preparation and serialize simultaneous identical requests. New output,
settings, code or runtime identities remain separate. No existing plans, results,
weights or retained versions are deleted or rewritten.

Moved potentially expensive plan verification outside the global job registry
lock. The worker still verifies the immutable plan again under the execution
lease before running. Kept inherited execution leases: removing them would permit
concurrent GPU work after a worker crash while a child survives.

Added descendant supervision that records observed PID/start-time identities,
retains children after reparenting and signals owned descendants even if they
change process group. Stop retains the lease until observed children have exited;
resistant children receive SIGKILL after the existing grace period. A workflow
that exits leaving observed children is failed and cleaned up, not reported as
success. Process inspection reads PID/parent/group/start metadata, not command
arguments or environments. It does not infer ownership from an open lock file.

The native BrokerClient has no three-minute timeout and no automatic submission
retry. It waits for the subprocess result. No invented timeout setting was added.
The first preparation still verifies/copies required model data; retry reuse is
not a relaxation of model/runtime verification before inference.

## Results

No neural inference or model throughput benchmarks were run.

| Inert reproduction | Released 0.2.3 | Candidate |
|---|---|---|
| Same saved request submitted twice | Two plans and two runtime views | One plan and one view |
| Four simultaneous identical preparations | Not run | One build, one plan, one view |
| Stop child using `setsid`, ignoring TERM and inheriting execution lease | Child survived; lock remained held after worker returned | Child exited; independent lock acquisition succeeded |

The real-process paired cancellation reproduction is saved in
`artifacts/0186-repair-submission-retries/reproduce_cancellation.py`; its JSON
records only fixture outcomes, with no student data. Additional regressions cover
PID reuse, reparenting, unrelated processes, changed settings/code, corrupted
plan references, interrupted preparation, code/runtime preservation and queue
serialization. **54/54 fast-suite commands passed**, including six plan-reuse
cases, three process-tree identity cases and nineteen native-job cases. Six
XCTest cases and executable Swift harnesses passed; `swift build` passed. The
two optional dependency-specific resident fixtures retain their explicit skips
in the generic Python environment. Publication verification follows below.

The execution lock is acquired only after a queued job record is written. A
leftover holder can block execution, but cannot by itself account for plans
that never become job records. First-time preservation can still be expensive;
there is no measured three-minute timeout or retry mechanism in native submission.

## Decision and rationale

Fix stable request identity and descendant cleanup rather than deleting locks,
removing crash protection or suppressing scientific errors. A process merely
opening `execution.lock` may be waiting for it; `lsof` alone does not establish
lock ownership. Existing saved jobs retain their frozen worker code. New jobs
use this correction; old worker snapshots are not silently migrated.

## Reproduce

```bash
python3 Tests/test_plan_reuse.py
python3 Tests/test_process_tree.py
python3 Tests/test_desktop_jobs.py
python3 lab_book/artifacts/0186-repair-submission-retries/reproduce_cancellation.py
python3 Tests/run.py
swift build
```

The cancellation reproduction intentionally starts and stops only owned inert
fixture processes in temporary directories; it does not inspect/stop live jobs.

## Limits and what was not tested

The exact student's calibration stall and source of repeated requests remain
unconfirmed. No inference on that target, student hardware or fresh Mac was run.
Observed-process supervision is not a security container for deliberately evasive
double-fork daemons that reparent entirely between observations; supported engine
workers must remain supervised. A process stuck in an uninterruptible kernel
operation may keep the lease and Stop pending until macOS returns. Frozen older
jobs keep their original cancellation code. No screen-recording/accessibility
permission is required by Studio's own CLI/MCP diagnostics.

## Next

For a Mac already affected by the older worker, restart macOS to end orphaned
processes safely, install the corrected app, and use a new submission. Preserve
existing outputs and diagnostics; do not delete the lock or hand-edit snapshots.
