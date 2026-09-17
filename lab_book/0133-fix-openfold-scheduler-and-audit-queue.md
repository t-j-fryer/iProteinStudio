---
entry: 0133
title: Fix OpenFold scheduling and audit stalled desktop batches
date: 2026-09-16
author: GPT-6
type: bugfix
status: complete
machine: local Apple Silicon Mac; no performance measurements
tags: [openfold3, queue, scheduler, audit, ui]
---

## Context

The user reported a desktop batch ending with `--design-scheduler resident has no
validated worker for predictor openfold-3-mlx` immediately after successful
IntelliFold Full completion. Three queued batches in Bgx shared this failure.
This follows [[0129-queue-all-studio-workflows]] and the resident-worker policy
in [[0046-implement-campaign-resident-predictors]].

## What was done

- Fixed `Core/CommandBuilder.swift` to choose `run` for OpenFold-3 with one GPU
  owner. This matches the already-correct MCP iterative planner. Other engines'
  policies and scientific settings are unchanged.
- Added rejection in `mcp/iprotein_mcp/desktop.py` for unsupported OpenFold
  residency before any engine in a native batch starts. Kept the shell runner's
  original fail-loud guard.
- Added minibinder/nanobody and multi-engine Swift request regression coverage;
  corrected an older test that incorrectly demanded residency for OpenFold.
  Added real inert-worker desktop/batch regression tests and real runner CLI
  configuration checks accepting `run` and rejecting `resident`.
- Inspected broker error/log tails and saved run/batch receipts read-only. Called
  MCP engine detection (all required components report `ok`) and result overview.
  Global `runs_list` encountered an unrelated Validation symlink path error;
  project-scoped `runs_list` succeeded. No changes to Validation were made.
- Audited all completed artifacts, summary cardinality and referenced structures.
  Saved [report](artifacts/0133-openfold-queue-audit/REPORT.md),
  [audit script](artifacts/0133-openfold-queue-audit/audit.py), CSV and JSON evidence.
- Updated CLI scheduling documentation. Built and signed the local debug app at
  `build/iProteinStudio.app`; this is the user's currently running app location,
  so it needs reopening to load the new executable.

## Results

No performance measurements — implementation and existing-output audit only.

| Observation | Count |
|---|---:|
| Completed engine/scaffold campaigns | 60 |
| Completed optimized run/cycle structures | 4,500 |
| Completed cycle-00 starts | 900 |
| Verified saved artifact SHA-256 digests | 49,256 |
| OpenFold campaigns failed before inference | 3 |
| Subsequent OpenFold campaigns never started | 7 |
| Outstanding optimized structures | 750 |
| Active or queued broker jobs | 0 |

The global queue continued after failures; seven unstarted child manifests were
misleadingly initialized as `running`. These counts are not independent hits.

Validation passed:

- `python3 Tests/run_swift_contracts.py` (all request/controller/result harnesses).
- `python3 Tests/test_desktop_jobs.py`: 18 tests.
- `python3 Tests/test_iterative_engine_batch.py`: 10 tests.
- `bash Tests/test_iterative_cli_contract.sh`.
- `swift build --disable-sandbox --skip-update` with writable compiler caches.
- `bash build_app.sh debug`, including app code-signature verification.
- `git diff --check`.

The first default Swift build failed because the sandbox denied the compiler
cache path and then emitted misleading SDK errors. A build with SDK 15.4 and
writable caches passed; the final build and packaged app also passed with the
normal SDK and writable caches. The first Swift harness run exposed the old
incorrect OpenFold residency expectation; correcting it made the suite pass.

## Decision and rationale

Use the existing supported per-trajectory policy rather than inventing an
unvalidated resident worker or silently changing the runner's interpretation of
an explicit request. Reject invalid native requests at preflight to avoid
waiting days for a final-engine validation error. Preserve completed results,
immutable saved plans and frozen scientific code; do not rewrite historic plan
digests or rerun completed engines.

## Reproduce

From the canonical repository:

```bash
python3 lab_book/artifacts/0133-openfold-queue-audit/audit.py
python3 Tests/run_swift_contracts.py
python3 Tests/test_desktop_jobs.py
python3 Tests/test_iterative_engine_batch.py
bash Tests/test_iterative_cli_contract.sh
CLANG_MODULE_CACHE_PATH=/tmp/iprotein-openfold-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iprotein-openfold-swift-cache \
  swift build --disable-sandbox --skip-update
CLANG_MODULE_CACHE_PATH=/tmp/iprotein-openfold-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iprotein-openfold-swift-cache \
  bash build_app.sh debug
```

## Limits and what was not tested

No new model inference, timing measurements, interactive UI acceptance or
scientific-quality validation. Unrelated pre-existing RFD3 source changes were
preserved; the local build includes the current working tree. No changes to
live jobs, frozen plans, manifests or completed scientific outputs. The app
process was not interrupted. No commit or release was published.

## Next

Reopen the rebuilt app. The unfinished jobs remain paused. To recover them,
create new immutable preflight plans for the ten incomplete OpenFold campaigns
using their original saved scientific settings and pipeline snapshots, explicitly
recording only the scheduling correction. An unchanged Resume of the original
failed batch still contains the invalid resident command. The user was offered
restart or leave-paused; absent a restart choice, no inference was launched.
