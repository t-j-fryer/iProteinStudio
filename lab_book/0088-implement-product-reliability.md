---
entry: 0088
title: Implement workspace recovery, durable native jobs and product boundaries
date: 2026-09-04
author: gpt-6
type: implementation
status: implemented; GUI and release acceptance pending
machine: Apple M4 Max, 64 GB unified memory (existing project provenance)
tags: [architecture, reliability, accessibility, workspaces, jobs, testing]
---

## Context and scope

The user approved implementing the product/repository improvements from entry
0087. Work was performed in the canonical iProteinStudio checkout on top of the
existing uncommitted secondary-structure-prior feature. That feature, its build
number and its validation campaign were retained. No commit, push, installed
runtime refresh, model download or new inference campaign was performed.

## Changes

- Added a small `StudioCore` library with atomic, validated JSON persistence,
  previous-copy recovery, preserved corruption evidence, a filesystem/index
  transfer journal, a shared execution lease and allowlisted support reports.
  Workspace save failures restore the last saved UI state. Unrecoverable indexes
  pause editing. Archive replaces permanent deletion and Restore returns files
  to their original checkpoint paths. Queued/active work and execution ownership
  guard transfers; crash recovery distinguishes pre-commit and committed moves.
- Added a native client of the existing durable bridge. Iterative, Predict,
  RFdiffusion3, target preparation and calibration save their settings before
  registration. The private native adapter freezes commands/inputs into immutable
  plans, retaining scientific argv, alignment policy and scheduler overrides.
  New workers copy the bridge, share the MCP execution lock, recheck provenance
  after queueing, and own cancellation of the entire child process group.
  `stopping` remains active until children exit. Stop during submission is retained.
  Resume cannot overlap a live prior worker. Active jobs are not lost to history
  limits, and plan idempotence scans beyond the recent-history window.
- Native controllers and Activity observe the job registry; app startup reattaches
  workspace campaigns. Older running workers cannot safely adopt the new signal
  protocol and must be stopped through their original client. The new bridge
  refuses incompatible cancellation instead of releasing their lease early.
- RFdiffusion3 uses the production foreground campaign scripts under the durable
  worker. Successful preparation saves hashes of config/assets; Retry verifies
  and reuses them. Target prediction creates separate attempt directories and
  promotes the current-result pointer only after success, including when the app
  has quit. A failed attempt preserves the prior cache. Calibration keeps unique
  output directories rather than deleting previous measurements.
- Installation, repair, resource staging and destructive runtime maintenance now
  acquire the same execution lease. App updates defer staging while jobs run.
- Iterative dashboards use saved workspace identity, request and threshold.
  Prediction and RFdiffusion3 dashboards are also scoped to their source workspace.
  Validation has a typed issue list shared by Start availability and explanation,
  with a Review field action. Error cards offer a preview and local export of a
  report that excludes arbitrary logs, sequences, chemical input, paths and tokens.
- Named native sliders and engine checkboxes, named web playback/frame controls,
  accessible cycle descriptions, reduced-motion handling and smaller window/pane
  minimums address the concrete source-level accessibility gaps from the audit.
- Extracted filesystem result discovery from the model file into `Core/Results`.
  Result requests coalesce off the main actor with a bounded short-lived cache;
  metadata changes during reading retain the previous snapshot. History and
  metrics also scan off the UI actor. Live metrics retain observed checkpoints
  across partial writes. Duplicate CSV headers and incomplete rows cannot crash
  the result reader or create a partial result.
- Added `Tests/run.py`, an XCTest target, executable core contracts and CI.
  Python scripts execute their real entry points, and reports explicitly list
  failures and unperformed acceptance. Added staged upstream vendoring with a
  tracked ownership/hash manifest; automatic replacement of the Studio-modified
  runner is refused. Apply verifies the complete review, keeps backups and rolls
  back replacements on an I/O failure. It is not multi-file crash-atomic.
- Rewrote `ARCHITECTURE.md`, added `docs/TESTING.md`, and updated README, CLI and
  change notes to describe these actual boundaries.

## Validation performed

The deterministic suite was run twice, with the final whole-suite report at
`/tmp/iproteinstudio-final-contracts.log`:

```bash
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  python3 Tests/run.py --scratch-path /tmp/iproteinstudio-reliability-build
```

**24 of 25 commands passed.** The sole failure is `swift test`: this machine has
Command Line Tools without an available `XCTest` module. The suite deliberately
remains failed; it does not silently substitute or skip the test target. Full
Xcode/XCTest execution is still required. The initial default SDK/toolchain
combination was incompatible, so compilation used the compatible installed 15.4
SDK. No Xcode installation or system configuration was changed.

The executable Swift contracts passed independently after the final parser
changes. They run corruption recovery, failed-write rollback, archive/restore,
crash replay before/after index commit, lease exclusion, support-report content
checks, prediction/result discovery, malformed CSV handling, saved checker
verdicts and iterative command generation. These execute real temporary-file
operations; they are not syntax checks or an XCTest result.

```bash
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  python3 Tests/run_swift_contracts.py
```

The final desktop-job tests exercise nine fixture cases: native/MCP serialization,
queued script/input tampering, resistant-child cancellation, fixed iterative
commands, preparation reuse/tamper rejection, bounded output paths, history-limit
idempotence and legacy-worker cancellation refusal. These use temporary fake
workers, not installed scientific models. Existing MCP bridge tests also passed
in the complete deterministic run. Process/loopback integration required approved
sandbox escalation. Vendoring stage/refusal/tamper tests passed using a synthetic
upstream and mocked revision lookup; no real upstream sync was applied.

All **eight science fixture commands passed** using the existing prepared RFD3
Python environment:

```bash
python3 Tests/run.py --suite science \
  --science-python /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python
```

This ran workflow, partial-diffusion, motif scoring, worked-example, surface-origin,
target-export, aCbx-integrity and ligand-conditioning fixtures. Network responses
in the ligand checks were mocked. The report is temporarily available at
`/tmp/iproteinstudio-science-contracts.log`. No models were loaded for inference.

The app was built with:

```bash
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-reliability-modules \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iproteinstudio-reliability-modules \
  swift build --triple arm64-apple-macosx15.0 \
  --scratch-path /tmp/iproteinstudio-reliability-build
```

A cleanup build caught an inadvertently removed prediction configuration type;
it was restored before the final successful build. `git diff --check` passed.
No performance benchmark or inference speed/quality improvement is claimed.

## Limits and follow-up acceptance

- No interactive GUI/VoiceOver session, focus-order audit, enlarged-display or
  contrast assessment was performed. Source labels and fixture checks do not
  establish accessibility acceptance.
- No actual native app crash/relaunch, two-workspace GUI interaction, new
  real-model end-to-end run, M1 run, packaged release, Gatekeeper, signing or
  Sparkle acceptance was performed. Fake-worker and filesystem crash-replay
  checks cover underlying contracts but not the full application interaction.
- XCTest requires a full Xcode test environment. CI was added but not run remotely.
- Result caching is bounded polling, not a persistent index. No large-campaign
  responsiveness measurement was performed; a partial write that remains stable
  between reads can still require a subsequent poll for complete data.
- Vendoring failure rollback is implemented; the executable vendoring test covers
  staging and refusal/tampering, not a power failure during apply. Original bytes
  remain in the review directory for recovery.
- Target-library metadata still uses its existing index/reconciliation layer;
  workspace recovery does not constitute a migration of every cache/index in the
  application. Broader persistence consolidation remains incremental.
- The existing secondary-prior campaign was not resubmitted, cancelled, restaged
  or interpreted as validation of these changes. Apply runtime/UI acceptance
  after that work can safely release its installed runtime.
