---
entry: 0298
title: Expose Protein Hunter sequence modes as workflow tabs
date: 2026-10-05
author: GPT-6
type: implementation
status: complete
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1
tags: [protein-hunter, ui, partial-redesign, motif-scaffolding]
---

## Context

The user requested separate Protein Hunter partial-noising and motif-scaffolding
tabs matching the existing RFdiffusion3 workflow navigation.

## What was done

Moved the existing native-mode dropdown into a top-level segmented picker with
De novo design, Partial noising and Motif scaffolding, immediately below the
Protein Hunter header. Each sequence-region mode exposes its own source-binder
card and applicable controls; card numbering follows the selected workflow.
The de-novo examples and nanobody scaffold selector stay on the de-novo route.
Selecting a region mode from nanobody switches to mini-binder, whose existing
settings support that mode. Sequence, region and motif fields are retained.
The normal type selector resets any dormant region-mode value before changing
from nanobody, avoiding unexpectedly entering an old mode.

Persisted values remain deNovo/partialRedesign/motifScaffolding. No planner,
engine, seed, noising algorithm or runtime setting changed. The top-level
explanation states that the constraints act on sequence and coordinates may move;
Boltz remains required for sequence motif scaffolding. Updated the existing
Protein Hunter stage guide.

## Results

No performance measurements — UI implementation only.

- Swift application build passed.
- Existing compiled/executed IterativeCommandContractHarness passed, including
  partial redesign, motif preservation and saved-request round trips.
- Development app assembled at build/iProteinStudio.app; code-signature
  verification passed (version 0.2.22, build 68).
- No scientific jobs started, paused or modified. Installed application and
  published releases were not replaced.

Logs: lab_book/artifacts/0298-protein-hunter-mode-tabs/.

## Decision and rationale

Reuse RFdiffusion3's segmented navigation pattern and the existing persisted
Protein Hunter modes. Introducing a second independent tab state would allow the
visible workflow to disagree with the actual submitted request.

## Limits and what was not tested

No interactive visual verification: the native computer-use backend failed on
the preceding task. No new predictions were needed or run for this layout change.
The request/command harness tests pipeline behavior, not GUI clicks.

## Reproduce

Build with swift build --build-system native -j 2 and bash build_app.sh debug.
The existing Tests/IterativeCommandContractHarness.swift is compiled with the
iterative model/core sources listed in Tests/run_swift_contracts.py and executed.
