---
entry: 0155
title: Show NISE structures and progress throughout preparation and optimisation
date: 2026-09-18
author: GPT-6 Codex
type: bugfix
status: in-progress
machine: Apple M4 Max, 64 GB unified memory
tags: [nise, results, ui, checkpoints]
---

## Context

The active biotin NISE campaign had completed its initial backbones and was
folding Phase 0 refinement candidates, but Overview and Structures appeared
empty. The app only loaded `candidates/*.json`, which are written during checks
and scoring after folding; it ignored the already committed prediction receipts.
History also disabled results until a candidate file appeared.

## What was done

Added a presentation-only NISE reader for completed prediction journals, scored
candidate records, initial geometry assessments, RFdiffusion3's committed initial
set, NESSO shortlist receipts, beam advancement and final apo assessments. A scored
record replaces the live fold with the same identity. No new science, settings,
predictor execution or campaign-output writes are involved.

Dedicated results navigation separates Phase 0 preparation, Phase 1 optimisation
and final checks. Phase 0 stage names follow the saved refinement-round count;
Phase 1 separates cycles. Structures group by original lineage or trajectory.
Phase/stage/check-status/search controls are shared by Overview and Structures.
Stage counts remain whole-phase counts, while distributions follow the selection.
Final checks pair an apo structure with its exact holo candidate without counting
it twice in Phase 1 progress. Saved beam membership is separate from eligibility.
Missing geometry decisions and affinity scores remain unknown, never failed/zero.

The reader skips raw batch copies, native caches and unfinished outputs. It
allows historical absolute paths only within the run; copied fold receipts can
relocate through their explicit relative file inventory. Missing/unreadable or
escaping artifacts produce a visible warning. It uses off-main-actor, coalesced,
bounded snapshots instead of fingerprinting the complete NISE tensor tree.

History permits opening phase progress before scoring. Corrected stale form help
that said 100 starts rather than the already-implemented 1,000 default. Build 40
release notes and docs/NISE.md describe the views and their interpretation.

## Results

The read-only live fixture loaded 1,447 structures at its recorded check:
1,000 initial backbones (422 initial geometry pass, 578 fail), and 447 of 1,266
cycle01 folds. These are existing-output counts, not a throughput measurement.

Synthetic contracts cover initial/refinement and optimisation phase separation,
pending checks, absent scores, candidate replacement without duplication, copied
receipts, external/symlink path rejection, NESSO counts, RFD3 starts, saved beam
selection, malformed records, and final checks. The full shared Swift contract
suite and `swift build` pass, including the history-entry regression. Its final
live fixture saw 1,450 structures (450 cycle01 folds) with no warnings. Shared Protein Hunter and RFD3
results UI contracts pass. No model inference was launched by these tests.

Logs: [validation artifacts](artifacts/0155-nise-live-phase-results/).

## Decision and rationale

Read the durable records already written by every route. A completed structure,
a geometry pass, scoring eligibility and next-cycle selection are different
milestones. Do not infer a hit, recompute the search, or hide completed structures
until the rest of their batch finishes.

## Reproduce

Run `Tests/run_swift_contracts.py`. For the optional existing-run assertion, set
`STUDIO_NISE_LIVE_RUN` to the biotin campaign directory. The fixture expects its
known 1,000 starts, 422 initial passes and at least 370 cycle01 completions.
The ordinary suite uses only temporary synthetic outputs and requires no models.

## Limits and what was not tested

No new biological validation, throughput benchmark, UI click/VoiceOver automation,
or model execution. RFdiffusion3 initial structures appear after its initial set
is committed, rather than displaying unvalidated generator intermediates. NESSO
sequences without a fold contribute to shortlist counts, not viewable structures.
Artifact receipts are parsed but their entire tensor inventories are not rehashed
on every UI refresh; campaign resume retains responsibility for integrity audits.

## Deployment

Pending packaging and app relaunch. Pipeline/MCP resources are unchanged, so no
campaign pause or runtime replacement is required.
