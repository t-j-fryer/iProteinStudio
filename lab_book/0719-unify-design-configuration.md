---
entry: 0719
title: Unify backbone design configuration and explicit search objectives
date: 2026-11-03
author: Codex
type: implementation
status: implementation-verified; GPU qualification pending
machine: Apple Silicon development host; no performance measurements
tags: [rfd3, rfd4, ui, mcp, cli, public-candidate]
---

## Context

The user requested shared public/beta design configuration: multiple nanobody
frameworks with controllable allocation, intelligible target/framework MSA
controls, configurable search objectives and compatible ligand predictors,
shared RFD3/RFD4 molecule preparation, and visible clickable RFD4 epitopes.
Public delivery is prepared locally; publication was not explicitly requested.

## What was done

Implemented new optional request fields in Swift, CLI normalization and MCP
schema; weighted interleaved framework/conformer starts; native preparation
per framework/conformer/length; catalogue-specific CDRs and MSAs; objective
selection with missing-score rejection; ESMFold2 ligand-confidence prediction
through the existing NISE complete-sequence/atom-map adapter; shared molecule
analysis and native RFD4 atom conditions; target structure residue picker;
one backbone-generation entry in the custom builder.

RFD4 atom controls use the pinned upstream `RasaEnum` (buried=1, exposed=3)
and `HBondEnum` (donor=1, acceptor=2, both=3), read from the installed pinned
RFD4 source. RFD3 condition values are not forwarded unchanged.

## Results

No performance measurements or scientific campaign. Checks completed:

- Full RFD4 discovery: 47 tests passed, including native CPU authoring/auditing
  of the eight catalogue frameworks and new framework/conformer input cases.
- Focused backend suite: 39 tests passed. Final native reward/design-control
  suite: 11 passed, including the pinned upstream reward aggregator with a
  nondefault objective. These suites overlap; counts are not additive.
- Final broker/snapshot/configuration suite: 70 passed, including inert queue,
  cancellation/resume, retained-code and privilege-profile regressions.
- Final snapshot/design-control suite: 12 passed. It checks stale installed
  scripts versus saved preflight scripts and retained execution code.
- Final native ligand input audit after the snapshot fix: one passed. Imported
  ethanol conformer geometry, canonical-to-native atom identities, and requested
  buried/exposed/H-bond conditions survive the actual upstream CPU feature prep.
- Swift request, workflow and result harnesses: three passed. Swift builds passed
  in beta and the public candidate. Both local app packages were built and their
  ad-hoc signatures verified by the existing packaging scripts.
- UI inspection confirmed the unified backbone entry and RFD4/RFD3 generator
  selector in the built beta app. No design was submitted during inspection.
- Scoped public transfer and whitespace checks passed. No commit, push,
  publication, installation or stable-app replacement was performed.

Early checks caught and corrected a canonical ligand atom-name fixture mismatch.
Broad broker checks initially failed because the sandbox could not read host
memory, then because an inherited installed-runtime environment overrode their
synthetic project fixtures. Final broker outcome is recorded below. Those
failed invocations are not counted as successful checks. A final public sync
initially copied a beta-only result reader; compilation caught its private type
dependencies. Restored the public baseline files and reapplied only the scoped
task patch. All 37 tracked source/test/doc patches were compared line-for-line
(additions/removals), preserving each branch’s existing code.

## Decision and rationale

Retain the existing broker, job-scoped caffeinate command, resident adapters,
cycle waves, per-unit receipts and frozen workflow snapshots. Framework and
conformer allocation occurs inside that execution contract. Native rollout search uses the selected scalar score through the existing
upstream reward aggregator; the sampling/search implementation is unchanged. Preserve old task defaults when the new fields are absent.
Affinity objectives require Boltz; ESMFold2 ligand routes expose confidence.

Final integration review found RFD4 preflight still selected installed scripts,
although the GUI saved a pipeline snapshot. Preflight now reads its saved
snapshot; CLI/MCP retains its shipped pipeline before preparation. Plan capture
uses the same source for RFD4, then the existing runtime view rewrites execution
into the retained code. Shared installed scripts are unchanged. The generic
snapshot API's existing default is preserved for other workflows. Multi-input
preparation timeout scales with authored variants. This is a code-retention fix,
not a new launcher; broker locks, admission, pinned models, caffeinate and
checkpoint behavior remain in the established path.

## Reproduce

Run the RFD4 unit/native-input suites using the existing RFD4 Python runtime,
with NANOHUNTER_ROOT pointing to the managed installation. Run the Swift
configuration harness, swift build and the local beta/candidate packaging
checks. Commands (set ROOT to this checkout and RUNTIME to the managed installation):

```sh
NANOHUNTER_ROOT="$RUNTIME" PYTHONPATH=Tests:tools OMP_NUM_THREADS=1 "$RUNTIME/venvs/NanoHunter_rfd4/bin/python" -B -m unittest discover -s Tests -p 'test_rfd4*.py'
NANOHUNTER_ROOT="$RUNTIME" PYTHONPATH=Tests:tools OMP_NUM_THREADS=1 "$RUNTIME/venvs/NanoHunter_rfd4/bin/python" -B -m unittest test_code_snapshot test_rfd4_design_controls
NANOHUNTER_ROOT="$RUNTIME" PYTHONPATH=Tests:tools OMP_NUM_THREADS=1 "$RUNTIME/venvs/NanoHunter_rfd4/bin/python" -B -m unittest test_rfd4_configuration_inputs.NativeInputs.test_ligand_controls_and_imported_conformer_reach_native_features
STUDIO_SWIFT_CASES=rfd4_configuration,recommended_workflows,results python3 Tests/run_swift_contracts.py
bash release/build_local_beta.sh
# In .worktrees/paper-release:
bash build_app.sh debug
```

The broker fixture suite must run without NANOHUNTER_ROOT so its temporary
IPROTEINSTUDIO_TEST_SUPPORT_ROOT takes effect, with host memory/process inspection
available. It uses inert scripts, not models.

Evidence logs and a scoped source hash inventory are under
`lab_book/artifacts/0719-design-configuration/`. Test durations are verification
wall time, not scientific performance benchmarks.

## Limits and what was not tested

No GPU inference or experimental binding validation for the new combinations.
No claim that different engine confidence scores are calibrated comparably.
No installed runtimes, active job settings, model assets or raw scientific
outputs changed. Native rollout search does not accept multiple frameworks,
multiple conformers in this change. RFD3 fixed-framework
nanobodies remain excluded. Additional ligand predictors beyond Boltz and the
existing ESMFold2 adapter are not newly qualified by this work.

## Local artifacts and next step

- Beta: `build/iProteinStudio Beta.app`, version 0.2.31-dev (77).
- Public candidate: `.worktrees/paper-release/build/iProteinStudio.app`, version
  0.2.31 (77), development channel. Neither artifact enables automatic updates.

GPU qualification remains outstanding before release promotion: multi-framework
search, multiple conformers and the newly exposed ESMFold2 ligand objectives.
This change does not qualify experimental affinity or binding efficacy. Full
interactive molecule/PDB lookup and every structure-picker action were not
exercised; their shared components were reused, with native atom conditions
covered by the CPU audit. Publication still requires an explicit release request.
