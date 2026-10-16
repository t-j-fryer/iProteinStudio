---
entry: 0322
title: Unify Protein Hunter epitope guidance across generation and refinement
date: 2026-10-06
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [protein-hunter, boltz, protenix, rfd3, ui, mcp]
---

## Context

The user requested one protein-hotspot interface for Boltz 2, Protenix Constraint
and RFdiffusion3 starts, with optional continued guidance during refinement.
Other refiners should remain available and clearly disclose loss of epitope
conditioning. Existing shared metadata was usable, but UI capability depended
on the starting engine and the Protenix adapter did not receive a CLI hotspot
override when the template contained another selection.

## What was done

- Added persisted `DesignRequest.refinementEpitopeGuidance`, default true,
  backward-compatible when absent. Target controls now consider both stages.
- Added a refinement toggle and stage/engine explanations, highlighting
  unsupported refiners. Target positions are checked against sequence lengths;
  newline-separated residue lists are supported.
- Added CLI/MCP argument `--refinement-epitope-guidance auto|off` to the recorded
  command. `auto` retains guidance in supported stages; `off` removes the shared
  hotspot conditioning in cycles 01 onward, preserving cycle 00. Independent
  checks remain unrestrained.
- Applied policy in both resident/cycle-wave and ordinary per-trajectory YAML
  generation. Protenix inputs now use the resolved hotspot list (including CLI
  override), preserving its separate pocket distance. Boltz retains the existing
  pocket/CDR3 builder and forced-contact steering behavior.
- Separate-engine initialization saves its own scoped template, allowing an
  unsupported starting engine followed by a guided refiner. Refinement templates
  and CLI overrides are scoped independently. Handoff records the chosen policy
  and refinement capability. Original scientific requests remain immutable.
- Extracted and tested RFdiffusion3's mapping of target-sequence positions to
  source chain/residue numbers, including gaps and `B:2` syntax.
- Added CPU regression tests to the science test list and documented controls,
  numbering, engine-specific mechanisms, provenance and limitations in
  `docs/PROTEIN_HUNTER_STAGES.md`.

## Results

No performance or binding-quality measurements — implementation and CPU tests only.

- 18 Hunter CPU tests passed, including real shell YAML generation and real
  Protenix JSON conversion, a 24-case method/refiner/policy matrix, blind checks,
  CLI override, invalid options, MCP parsing and RFD3 numbering translation.
- Swift contract harnesses passed, including request round-trip, old-workspace
  defaults, refinement capability, emitted arguments and target position bounds.
- `swift build` passed. Shell syntax and `git diff --check` passed.
- The wider `Tests/test_workflow_pipelines.py` stopped in an unrelated existing
  RFD3 ligand fixture: the fixture lacks `nanohunter_root`, required by
  `run_rfd3_nise_campaign.py:246`. It did not reach its later contract checks.
  The failure is retained, not counted as a pass.

Logs: `lab_book/artifacts/0322-epitope-stage-guidance/`.

## What was not tested

No GPU generation/refinement campaign, new epitope-steering efficacy experiment,
or interactive GUI session was run. No running job was changed. The installed
app/runtime and published release were not replaced. Source checkout contains
other ongoing work; those changes were preserved.

## Interpretation

A shared selection does not make the underlying mechanisms identical. Boltz uses
its existing 6 Å pocket restraint plus nanobody CDR3 contact where applicable;
Protenix Constraint uses its trained 8 Å token-centre prior; RFD3 uses hotspots.
Neither conditioning nor high confidence proves that the intended epitope was
bound. The prior Protenix steering limitation remains documented.

## Follow-up — broader test repaired

[0323](0323-repair-workflow-test-fixture.md) fixes the missing fixture root and a
subsequent stale Protenix default assertion. The complete workflow contract test
now passes, as do all nine prediction-profile tests. The earlier failure log is
retained as historical evidence.
