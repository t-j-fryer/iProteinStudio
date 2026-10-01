---
entry: 0252
title: Separate Protein Hunter initialization and refinement
date: 2026-10-01
author: Codex
type: implementation
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, predictors, ui, mcp, release]
---

## Context

User requested RFdiffusion3 cycle-00 starts and an independent starting predictor,
particularly followed by ESMFold2 Fast refinement. Legacy X-token workflows must
remain reproducible.

## What was done

Explicit stage coordinator reuses the established Hunter runner and RFdiffusion3
preparer. Generator completes and releases its model before refinement loads.
Cycle-00 output cardinality/coordinates/chain lengths are checked and hashed.
MPNN produces complete sequences before ESMFold2 sees any inputs. App, CLI and MCP
expose the same recipe. Generation restraints have explicit stage scope; ESMFold2
refinement has no pocket/template guidance. Existing checkpoints do not migrate.

## Results

Swift build and 13 Swift tests pass. Swift command/results contracts, original
CLI contract, 10 CPU handoff tests, 5 live-result tests, 23 MCP tests and 25 desktop
job tests pass. Runtime-binding/code-snapshot tests and current documentation
links pass. The final MCP rerun needed process/socket permissions: the restricted
sandbox attempt was interrupted; the authorized complete run passed.

Real-model RFdiffusion3 → ESMFold2 Fast (2 starts, 4 refined structures), Boltz →
ESMFold2 Fast and Full (1 start + 2 refined structures each) pass. A separate Full
run was interrupted after cycle 01 and resumed through the immutable plan; saved
start/cycle-01 hashes stayed identical. One resident model load serves both
cycles in uninterrupted runs. Ligand mapping acceptance is queued behind the
user's separate ESM benchmark. No speed or design-quality claim. See
Validation/lab_book/0077-hunter-stage-acceptance.md.

## Decision and rationale

Reuse the established refinement loop rather than introduce a second scientific
algorithm. Fixed-framework nanobodies cannot use de novo RFD3 initialization.
ESMFold2 cannot initialize X-token starts. Target structure matching is exact.

## Reproduce

Run Tests/test_hunter_stages.py in a managed environment with PyYAML;
Validation/experiments/hunter_stages_v1/preflight.py creates immutable normal
iterative plans sharing Studio's execution lock. Evidence:
lab_book/artifacts/0250-hunter-stages.

## Limits and what was not tested

No wet-lab validation or cross-engine score calibration. Not every possible
engine pair, target size or nanobody framework was tested. No fresh-Mac install,
VoiceOver audit, prolonged memory soak or real Sparkle upgrade on a second Mac.
Ligand acceptance and distribution verification remain pending.

## Next

Finish tests, publish app/MCP/CLI release, restore paused benchmark and queue.

## Updated queue handoff (user request, 2026-10-01)

After GPU acceptance, the ESMFold2 Full 3/50 benchmark takes priority over resuming Protenix. The dedicated watcher owns resumption. Do not independently resume the two paused jobs. See [queue handoff](artifacts/0250-hunter-stages/QUEUE_HANDOFF.md).
