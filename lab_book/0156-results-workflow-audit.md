---
entry: 0156
title: Audit result organisation and score provenance across workflows
date: 2026-09-18
author: GPT-6 Codex
type: bugfix
status: in-progress
machine: Apple M4 Max, 64 GB unified memory
tags: [nise, nesso, prediction, rfd3, results, ui]
---

## Context

The user asked whether the active biotin run had P(bind), requested compatibility
with NESSO and RFdiffusion3 NISE routes, and requested an audit of useful, robust
results views across Protein Hunter, RFdiffusion3 and Predict.

The initial broker/file check found 1,000 initial structures, 461/1,266 cycle01
structures, no affinity receipts and no scored candidates. This is expected:
initial generation omits affinity; the refinement batch finishes folding before
geometry checks and selective affinity evaluation. No search setting was changed.

## What was done

- NISE reads live NESSO screening receipts, including sequences outside the
  shortlist. Its dedicated score table separates NESSO probability/entropy/
  recorded screening score from Boltz probability and confidence. Matching name
  and sequence attach screening values to live folds. Screening decisions remain
  unknown until the shortlist commits; no historical objective is recalculated.
- Separate Boltz affinity receipts become visible before a whole scoring batch
  finishes, only when the candidate identity and structure-receipt SHA256 match.
- RFdiffusion3 initial receipts and configurable Phase 0 refinement stages are
  covered by route tests. No predictor metric is invented for generated backbones.
- Shared search, stage and score-source filters cover Protein Hunter, RFdiffusion3
  and Predict. Existing framework/engine filters, cycle playback, motif metrics,
  artifact roles and saved-hit semantics remain in place.
- RFdiffusion3 ranking promotes matching provisional models without hiding
  completed derivatives outside the shortlist.
- Predict opens results during execution and reads successful chunk receipts
  before its final CSV exists. Inputs group engine/model samples; template
  conditioning is labelled. Completed chunks and final CSV rows deduplicate.
  Final task failures appear separately and successful work remains visible.
- Removed premature result polling stops (including completed runs that may later
  resume). Prediction-library rows use the run name and permit partial results.
- Native confidence files cannot be borrowed from another sample; representative
  task scores are not broadcast across stochastic outputs. Ligand pLDDT remains
  separate from protein/complex pLDDT. Single-model Predict outputs read their
  matching affinity file; ambiguous shared affinity is not assigned to models.

## Results

`swift build` and all Swift contract harnesses pass. Targeted tests exercise live
NESSO scores, excluded sequences, separate probabilities, affinity hash mismatch,
RFD3 starts and variable refinement counts, retained unranked RFD3 predictions,
shared filtering, exact sample 1 versus sample 10 confidences, template labels,
live Predict chunks, unfinished-output exclusion and CSV deduplication. Existing
Protein Hunter and RFdiffusion3 UI contracts pass. The optional read-only biotin
fixture saw 1,471 structures: 1,000 starts and 471 cycle01 folds. These are output
counts, not a throughput benchmark.

[Build/test logs](artifacts/0156-results-workflow-audit/).

## Decision and rationale

Expose completed scientific units as they commit, retain earlier work, and keep
score sources and assessment stages explicit. Missing data is not zero. A
shortlist is a view of the candidate pool rather than permission to erase other
completed results. Computed scores do not imply experimental validation.

## Reproduce

`Tests/run_swift_contracts.py`, `Tests/test_iterative_results_ui_contract.sh`,
`Tests/test_rfd3_results_ui_contract.sh`, and `swift build`.
Optional STUDIO_NISE_LIVE_RUN points to the same existing biotin fixture used in
entry 0155. Tests create synthetic route/phase records; they do not run models.

## Limits and what was not tested

No new scientific inference, biological validation, throughput measurement,
VoiceOver or UI click automation. NESSO/RFD3 compatibility is checked against
saved-record schemas and synthetic route fixtures, not new GPU campaigns.
Predict exposes completed chunks, not uncommitted models inside an active chunk;
a failed task may only appear in the final CSV, with its log available meanwhile.
Shared input-level affinity for multiple stochastic models remains unassigned
when no explicit model correspondence exists. Existing compiler warnings remain.

## Deployment

Build 41 pending. Use an isolated release worktree because unrelated Validation
analysis edits are active in the main checkout. No pipeline/MCP runtime changes
or campaign pause are required for this presentation-only update.
