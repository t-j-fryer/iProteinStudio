---
entry: 0129
title: Queue all Studio workflows without blocking Start
date: 2026-09-09
author: GPT-6
type: implementation
status: complete
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
- Clean-source release packaging passed from `d5ad764d500e676588b724be835e8f3a56cdbfaa`:
  version 0.2.0, build 36, arm64. The release script passed deep/strict ad-hoc
  signature verification, packaged-resource checks and Sparkle archive signing.
  `hdiutil verify` passed, and both archive checksums matched `SHA256SUMS.txt`.
  DMG: `build/unsigned-beta-0.2.0-36/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`.
  SHA-256: `584a812f2b74f9cd0f807d2126133d5e29cea13e642264c46658f02673e3ad51`.
- Reopened the updated app through its normal quit/open lifecycle. Old app PID
  16422 exited; build-36 app PID 45805 opened. The existing job remained running
  under the same supervisor PID 16600 and child PID 16611. No job cancellation,
  resume, settings mutation or model launch was performed.

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
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules bash release/release_app.sh --unsigned-beta
hdiutil verify build/unsigned-beta-0.2.0-36/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg
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
broker and was observed for the existing running job; it is not an automatic
computer-reboot resume policy. The package is ad-hoc signed, not Developer ID
signed or notarized. No binary GitHub release was published.

## Next

Perform interactive queue/keyboard/VoiceOver acceptance using an isolated support
root when available. Source changes and this artifact audit are committed for the
authorized GitHub update; generated app/DMG artifacts remain outside Git.
