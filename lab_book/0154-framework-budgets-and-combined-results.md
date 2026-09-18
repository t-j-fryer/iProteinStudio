---
entry: 0154
title: Clarify framework budgets and retain combined batch results
date: 2026-09-18
author: GPT-6 Codex
type: implementation
status: in-progress
machine: Apple M4 Max, 64 GB unified memory
tags: [nanobody, budgets, results, mcp, release]
---

## Context

Following audit 0153, the user authorized reliable total/per-framework budget
controls, combined results with filters, and app/MCP/GitHub updates. Their
student's completed archive had correctly executed a saved 12-trajectory total;
the intended 100 per framework had never reached the saved batch.

## What was done

Added explicit Total across frameworks / Same per framework / Custom per
framework modes. A new optional request field preserves same-per-framework intent
across workspace reloads and selection changes; existing saved allocations keep
their old meaning. Child campaigns still save exact independent trajectory counts.
The launch summary separates trajectories, optimized cycle outputs and starts.
Valid text edits synchronously update the bound request, without Return/focus loss.
Invalid editors show inline errors and block Protein Hunter Start/Queue; no silent
clamping or submission of an older value. Numeric edits in other workflows also
apply immediately, but the invalid-editor submission gate is scoped to Protein Hunter.

Combined batch loading namespaces results by child campaign, preserving original
framework/engine identity, per-child thresholds, trajectory playback, cycle
boundaries and independent-check verdicts. Live batch dashboards and reopened
results show all children with framework/engine filters. History includes a
combined batch entry and individual children. Parent-history resume attaches to
the saved batch job; earlier results remain on disk and visible. Missing child
files produce a visible warning in the app and an explicit MCP error. Copied
archives relocate by campaign basename within the same workspace.

MCP contract 20 / server 1.13.0 discovers iterative_batch parents and accepts
framework_id/design_engine on results_overview. Groups carry artifact_run_id and
campaign_run_id; paths retain their child-relative meaning. Hit filtering precedes
trajectory limits. Guidance and docs distinguish trajectories from cycle outputs.
Build number 39; release notes updated. Prior authorized NISE batch-continuation
work and guidance-analysis records are included when publishing this working tree.
No model weights or student raw scientific outputs are added to Git.

## Results

- Swift request/controller contracts pass: immediate valid edits, invalid/empty/
  overflow/out-of-range edits, eight frameworks at 100 each = 800 per engine,
  custom/total conversion, persistence, child budgets, and parent-batch resume.
- Synthetic combined-results tests pass: duplicate run_001 identities across
  frameworks remain distinct; copied paths resolve; trajectory playback and
  saved verdicts survive; repeat loads retain earlier children.
- The student's unchanged archive loads as eight frameworks, 12 distinct
  trajectories, 60 optimized cycle outputs and 12 starts in the real Swift loader.
- MCP tests pass for batch discovery, framework/engine filters, limits, hit-only,
  budget counts, child-relative artifact ownership, missing children and symlink
  escape refusal.
- Fast release suite: 36/37 commands initially passed. One literal text assertion
  expected the old “optimized design” wording. Updated it to “optimized cycle
  outputs”; the affected UI contract then passed. Final Swift contracts rerun
  after adding parent-history resume also pass. Six XCTest tests passed.
- `swift build` and `git diff --check` pass. No inference used for these tests.

Logs: [artifacts](artifacts/0154-framework-budgets-and-batch-results/).

## Decision and rationale

Keep explicit user intent in the saved request, rather than assuming a number
always means a total or multiplying legacy budgets on upgrade. Combined results
reuse native per-campaign loaders and scientific verdicts; they never merge
same-numbered trajectories from different frameworks. Original science and raw
outputs remain unchanged. Existing batches gain the view without rerunning.

## Reproduce

`Tests/run_swift_contracts.py`, `Tests/test_framework_batch_results.py`,
`Tests/test_iterative_results_ui_contract.sh`, `Tests/run.py --suite fast`.
Set STUDIO_ARCHIVE_BATCH to the original student batch directory for the optional
real-archive loader assertion. Swift fixtures use inert jobs, not GPU inference.

## Limits and what was not tested

No biological performance validation, new scientific campaign, VoiceOver or
interactive GUI event automation. Numeric tests execute the same synchronous edit
helper used by the field but do not reproduce the student's exact old click
sequence. No new throughput claim. Packaged build, publication and local runtime
staging remain pending below; the biotin campaign will briefly pause through the
broker for the execution lease and resume its same immutable continuation plan.

## Next

Package and verify build 39, publish source and beta assets, relaunch the app,
verify installed MCP 20, and verify biotin checkpoint reuse after maintenance.
