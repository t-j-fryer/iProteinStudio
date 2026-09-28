---
entry: 0208
title: Publish completed native structures across all workflows
date: 2026-09-28
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 64 GB unified memory; model-free checks
tags: [ui, predictors, rfd3, nise, mcp, release]
---

## Context

Extend the Protein Hunter work in 0206/0207 to Predict, RFdiffusion3 and NISE,
including multi-input resident requests and independent verification. The user
also requested an app, MCP, GitHub and release update.

## What was done

Added atomic, display-only native writer receipts. Boltz, Protenix and OpenFold
writers are instrumented through the job-scoped import observer. IntelliFold
resident and CLI paths wrap its prediction/save function; the CLI retains its
upstream main body through a narrowly scoped AST decorator. No model calls,
tensors, scientific arguments or random state are changed. RFdiffusion3 publishes
each accepted backbone with the global index matching final bin/queue flattening.

The broker supplies each child campaign's output boundary. Observers come from
retained job code, including isolated module loading before child PYTHONPATH is
set. Live publication remains enabled when verbose engine telemetry is disabled.
Receipts require readable coordinates and confidence output (confidence is not
required for generated backbones); stale, missing and out-of-root files are
excluded. Multiple IntelliFold seeds have independent receipts.

Swift views merge native samples into Predict and RFdiffusion3, retain Protein
Hunter cycle and post/binder roles, and show NISE RFD3 Phase-0 starts before its
cohort receipt exists. Native initial IDs match later NISE lineage IDs. Existing
NISE fold journals cover Boltz structures for Boltz, NESSO and PSICHIC routes.
Shortlist verification folds also appear before their final report. Canonical
scientific results supersede previews. No geometry pass, hit, affinity value or
advancement is inferred from a completed structure.

MCP 31 provides native live_structures in results_overview and a virtual
live_predictions dataset in results_query; NISE overview also reads committed
fold journals and initial backbones. Protein Hunter examples start at ten
trajectories, carrying forward 0207. Documentation and 0.2.10/build56 release
metadata updated.

## Results

No performance measurements — implementation and model-free tests only.

- swift build passed; all Swift contract harnesses passed, including new
  per-input/engine, stale-file, chunk-promotion, post-role, parallel-backbone and
  pending NISE checks.
- Six native-writer/MCP publication tests and five resident Boltz publication
  tests passed. Writer names/layouts checked against installed upstream source.
- Fifteen progress/bootstrap/broker tests passed, including isolated retained
  module loading and real subprocess import instrumentation with telemetry off.
- Twenty-two MCP bridge tests and three combined-framework results tests passed.
- Thirty-four RFdiffusion3 regression tests passed using its managed interpreter.
  System Python and the older Boltz test interpreter lacked optional RFD3
  dependencies; rerunning in the actual RFD3 environment resolved those failures.
- Resident resume: 13 passed, one skipped (Accelerate CPU-loader fixture requires
  the IntelliFold environment). Both release shell contract checks passed.
- git diff --check passed. No model inference or live campaign mutation.

An initial import-hook recursion was caught by the subprocess test and fixed by
loading the sibling observer before installing the finder. A stalled test process
was stopped; the scientific worker was not interrupted. The broker test fixture
now supplies its durable state file, matching the production contract.

## Decision and rationale

Publish at explicit native writer return boundaries instead of polling arbitrary
coordinate files or breaking resident requests into individual submissions.
Preserve complete workflow records as selection/resume authority. UI refresh
intervals remain unchanged. Existing immutable jobs retain their original code;
shared runtime staging must wait for the execution lease, while the app can read
already committed outputs immediately.

## Reproduce

Run Tests/run_swift_contracts.py, test_live_structure_events.py,
test_live_iterative_results.py, test_engine_progress.py,
test_framework_batch_results.py, test_mcp_bridge.py, and
 test_resident_prediction_resume.py. Run test_rfd3*.py with the managed RFD3
interpreter. Run swift build and the two release contract shell tests.

## Limits and what was not tested

No new GPU inference, speed claim, changed scientific defaults, fresh-Mac install,
biological validation, or streaming of unfinished diffusion coordinates. Outputs
saved together by a native writer appear together. Frozen older jobs cannot gain
new publication hooks without changing their recorded code; their existing
completed outputs remain readable. Publication/deployment verification is recorded
below after the release is built.
