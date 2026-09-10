---
entry: 0129
title: Queue all Studio workflows without blocking Start
date: 2026-09-09
author: GPT-6
type: implementation
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, queue, broker, recovery]
---

## Context

The durable broker already serialized managed jobs across workspaces, but native
Start buttons blocked additional submissions. The user requested queueing and a
top-right queue icon, then explicitly extended the feature to Protein Hunter,
NISE, RFdiffusion3 and Predict. This is general application infrastructure; no
existing scientific run or settings were changed.

## What was done

- Removed cross-workflow Start blockers while retaining request, installation,
  ligand-input and submission-in-progress checks. Active work changes the action
  label to Add to Queue. Each submission saves its own configuration/output.
- Added `ManagedJobSession.detach()` and controller `prepareNewRun()` methods.
  They detach observation only, so New run and switching the displayed queue job
  never send cancellation. Pending submissions cannot be detached before the
  broker returns their durable identifier. Cancelled observation tasks cannot
  overwrite the newly displayed job.
- Added `JobQueueView` in the top-right toolbar: running/waiting work across all
  workspaces, workflow names, saved folder names, Show run, Show files, Cancel
  waiting work and Stop active work. Removed forced tab switches on workspace
  appearance. Supported Activity resumes can also enter the shared queue.
- Fixed a queued-worker startup cancellation race found by the integration test.
  A separate durable cancellation marker preserves stop intent during concurrent
  status updates. Signals wait until the new worker has installed its handlers;
  resume clears the marker. The capability is recorded only for newly created
  jobs, preserving compatibility with older frozen worker bridges.
- Added user documentation in `docs/JOB_QUEUE.md` and bumped the app to build 36.
  Existing execution-lock, immutable plan/provenance, resident-worker and
  per-cycle scheduling contracts are unchanged.

## Results

No performance measurements — implementation only.

- `swift build --disable-sandbox --skip-update`: passed after all app changes.
- `Tests/run_swift_contracts.py`: all six executables passed, including the
  actual four controllers linked to a mock job session. Tests verify independent
  Protein Hunter manifests across workspaces, switching all controllers without
  cancellation or relaunch, and guards for jobs without a durable ID.
- `Tests/test_desktop_jobs.py`: 15 tests passed. Inert subprocesses exercised all
  four native workflow adapters, shared-lock serialization, independent queued
  cancellation, stop/reap ownership, changed input/code rejection and resume.
  The mixed adapter fixture initially failed because its dummy shell runner
  lacked execute permission; correcting the fixture made it pass.
- `Tests/test_iterative_engine_batch.py`: nine tests passed.
- Iterative results UI contract and workspace organization/navigation contracts
  passed. The first workspace test attempt could not write the default Clang
  module cache and emitted cascading SDK errors; it passed with a writable
  `CLANG_MODULE_CACHE_PATH`, without changing the compiler or SDK.
- Release packaging and source publication audit will be recorded below after
  assembling the clean-source build.

## Decision and rationale

Use the existing durable broker instead of introducing a competing app-local
queue or concurrent GPU scheduler. Controllers own observation, not the lifetime
of detached jobs. Saved runtime snapshots remain authoritative for resumed work.
Do not advertise FIFO: lock acquisition currently has no strict ordering, so the
UI distinguishes submission-time display order from scheduling guarantees.

## Reproduce

From the repository root:

```bash
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules swift build --disable-sandbox --skip-update
python3 Tests/run_swift_contracts.py
python3 Tests/test_desktop_jobs.py
python3 Tests/test_iterative_engine_batch.py
bash Tests/test_iterative_results_ui_contract.sh
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules bash Tests/test_workspace_organization.sh
```

The broker tests use temporary support roots, fake adapters and synthetic inputs;
the NISE model preflight is mocked. They never access an installed model or run
scientific inference. Controller tests similarly never submit to the real broker.

## Limits and what was not tested

No GPU/model throughput, real campaign submission, scientific correctness,
fresh-Mac installation, reboot recovery, VoiceOver or automated GUI-click
acceptance. Existing jobs were not stopped, resumed or modified for these tests.
Old unmanaged RFdiffusion3 processes retain legacy monitoring; New run cannot
detach such an active process. Queue reordering, priorities and strict FIFO are
not implemented. App close/reopen durability follows the existing detached
broker; it is not an automatic computer-reboot resume policy.

## Next

Complete release artifact validation and source publication. Perform interactive
queue/keyboard/VoiceOver acceptance using an isolated support root when available.
