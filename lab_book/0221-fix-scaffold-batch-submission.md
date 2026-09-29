---
entry: 0221
title: Prepare one immutable plan for scaffold batches
date: 2026-09-29
author: Codex
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [nanobody, submission, protenix, ui, planning]
---

## Context

The student reports Protein Hunter / Protenix v2 nanobody submission remaining
at “Submitting saved settings…” with folders already saved, “Ready to resume”
in Runs, and no entry in Jobs. This places the reported delay before visible
job registration; it does not demonstrate stalled Protenix inference. No new
student logs were supplied, so the exact cause on that Mac remains unconfirmed.

## What was done

Traced RunController, ManagedJobSession, the desktop submission CLI, desktop_plan
and the broker. Iterative batch planning recursively persisted a full immutable
plan/runtime view for each scaffold, discarded those child plans, then persisted
the parent. Changed desktop.py to validate each child and gather provenance
without persisting it; the parent freezes one plan with all child commands,
runtime requirements and input provenance. No hashing, runtime binding, lease,
scientific setting or command checks were removed.

RunHistoryStore now shows an entirely prepared batch as Prepared, rather than
Ready to resume. Job-registry states still override the saved-file state.
RunController describes preparation before queueing and replaces its status
message with the actual error when submission fails, also logging that error.

## Results

An eight-scaffold temporary fixture reproduced nine calls to full plan
persistence before the fix and one afterwards. An invalid eighth scaffold
previously left seven child plans; validation now fails before any plan is
persisted. These are operation counts, not measured large-model speedups.

Desktop job tests include actual execution of eight inert scaffold workers
under one job, completion receipts, child-job associations, and rejection of
mutated template provenance. Swift contract tests exercise prepared, queued
and genuinely interrupted batch history. Runtime binding, code snapshot and
plan reuse suites pass, as do the desktop job suite, Swift contracts and
`swift build`. Logs are in build/0221-*.log.

## Decision and rationale

Keep one immutable execution plan for the combined batch. Independent child
plans were never submitted and added redundant runtime cloning/verification.
Do not disable integrity checks, impose an arbitrary timeout that could create
duplicate submissions, or diagnose an orphan GPU worker from a pre-job symptom.

## Reproduce

```bash
PYTHONDONTWRITEBYTECODE=1 python3 Tests/test_desktop_jobs.py
PYTHONDONTWRITEBYTECODE=1 python3 Tests/run_swift_contracts.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Tests -p 'test_plan_reuse.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Tests -p 'test_runtime_bindings.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Tests -p 'test_code_snapshot.py'
swift build
```

## Limits and what was not tested

No real model inference, fresh-Mac installation, student-machine reproduction
or elapsed-time benchmark. Single-scaffold submission may have a different
cause. The remaining parent runtime preparation can still take time; this fix
does not introduce detailed per-file preparation progress. No production jobs
or installed resources were changed. At initial validation these source changes were not yet packaged,
installed or published. They subsequently shipped in0.2.14 (entry0222).

## Next

Included in app0.2.14/build60/MCP35; see [0222](0222-release-submission-and-bulk-cleanup.md). If the student still
cannot reach Jobs, collect submission diagnostics rather than interpreting the
presence of saved campaign folders as evidence of an engine launch.
