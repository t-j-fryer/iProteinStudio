---
entry: 0095
title: Separate monomer initialization refinement from normal optimization
date: 2026-09-05
author: gpt-6
type: implementation
status: complete
machine: arm64, macOS 26.6.1; no hardware benchmark
tags: [secondary-structure, reproducibility, recovery, validation, mcp]
---

## Context

Following [[0094-bounded-assessment-journal]], the user narrowed the requested
implementation to unconditioned hallucinated monomers. The previous journal
recorded externally supplied artifacts and assessments but did not generate
candidates or integrate with the optimization scheduler. This change implements
that separate monomer path in shared pipeline code. Existing target-associated
Validation campaigns and their immutable outputs were not changed or executed.

The working tree already contained extensive uncommitted product and
secondary-structure work. Changes were made in place without reverting it.
Base commit: `37cc95497283025191e7d2067cb35d1af9168d72`; this is a dirty-tree
implementation, not a claim that the base commit contains these changes.

## What was done

Added `initialization_assessment.py` and `initialization_refinement.py` to the
shipped pipeline scripts. The assessor ports the existing Biotite P-SEA usage,
checks the exact requested monomer sequence, coordinates, assignment cardinality
and finite CA pLDDT, and records regional assessments. An explicitly configured
minimum run of consecutive coil residues individually below an explicit
confidence threshold selects regions for reconsideration. Short coil segments
and long confident coil segments do not trigger this criterion. There are no
new default acceptance thresholds or disorder-classification claims.

Extended the existing seed sampler with regional resampling that retains the
original position plan, applies the existing weighting rules, preserves all
unselected residues, and preserves the mask count inside the selected union.
Both existing sampling orders remain available. Existing released seed-stream
tests pass. Original sequences, masks and sampling settings are preserved;
each proposal independently records its seed, selected regions and actual changes.

The journal atomically publishes separate input, prediction and assessment
stages with SHA-256 receipts. Assessment also saves an explicit progression
decision. Selection is a separate scheduler action requiring an eligible
assessment. The budget includes the original initialization. Exhaustion remains
a recorded failure and prevents normal cycling. Resume verifies configuration,
policy, code identity and artifacts, and reuses complete stages independently.
CLI mutations hold an exclusive journal lock.

Integrated the stages into `nanohunter_run.sh`'s existing per-run scheduler.
The original cycle-00 files and metrics remain intact. An accepted initialization
supplies its own preserved structure and sequence to the cycle-00→01 MPNN
redesign. Initialization attempts never count as optimized designs; the campaign
budget records their separate maximum. Seed-only preferences remain seed-only;
applying them during MPNN requires the explicitly chosen seed-and-cycles scope.

CLI and MCP expose three required opt-in refinement policy flags. Preflight
requires a randomly initialized, unconditioned single protein on chain A with
empty MSA, an explicit seed, and explicit scope for any active sequence prior.
Templates, other chains, ligands, target restraints and unsupported schedulers
fail explicitly. MCP records the `run` scheduler in the immutable plan for this
path, adds all refinement helpers to script provenance, and continues through
the existing job_start/shared-lock machinery. Other plans keep their existing
scheduler. Added the shipped `examples/monomer_initialization.yaml` input and
protected the new files in the vendor manifest.

Coordinate assessment explicitly uses the managed Protenix environment's pinned
Biotite dependency. Detection reported installed engines; an import check showed
Biotite was absent from the Boltz environment and present as version 1.6.0 in
the managed Protenix environment. No environment was installed or modified, and
the requested prediction engine is never replaced by the assessment runtime.

## Results

No performance measurements — implementation and software fixtures only.

- 14 initialization assessment, sampling and journal tests passed, including
  stage-by-stage resume, configuration changes, corrupted artifacts, missing
  history, interrupted publication, concurrent proposals and explicit exhaustion.
- 6 monomer integration tests passed in the managed scientific interpreter.
  They execute the actual per-run shell scheduler with synthetic prediction and
  MPNN adapters and real Biotite coordinate assessment. They cover original
  acceptance, acceptance after refinement, the selected-structure handoff, normal
  cycling, no-work resume, exhaustion without inverse folding, input validation,
  and the full runner's CLI preflight.
- All 7 existing secondary-structure seed contracts passed.
- All 17 MCP bridge tests passed, including the new refinement plan contract.
  The subsequently updated workflow-guide rule and minimum-length preflight
  argument were checked again with their relevant targeted tests.
- Existing iterative CLI, design-cardinality and vendor-pipeline contracts passed.
- `swift build` and `git diff --check` passed.

The first MCP run failed solely because the filesystem sandbox prohibited its
loopback test server. Its full rerun with approved loopback access passed. The
first Swift build failed because SwiftPM's nested manifest sandbox could not
start; the approved ordinary `swift build` rerun passed. These were environment
restrictions, not skipped tests or source compilation fixes.

## Decision and rationale

Keep assessment, candidate generation and scheduling separate. Reuse the existing
sequence preferences rather than introducing a second set of biological weights.
Require explicit experimental eligibility criteria instead of promoting the
retrospective thresholds from earlier campaigns. Preserve the original cycle 00
rather than replacing it with the successful attempt.

Integrate with the existing per-run scheduler first. Resident and cycle-wave
retry accounting need separate implementation and validation; requests for those
combinations fail instead of switching schedulers inside an executing job. MCP
preflight makes the per-run choice explicit before execution. There is no
performance claim for that choice.

## Reproduce

From the canonical Studio repository:

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" bash Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh --detect
python3 Tests/test_initialization_refinement.py
MPLCONFIGDIR=/private/tmp/iproteinstudio-mpl "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" Tests/test_monomer_initialization_pipeline.py
python3 Tests/test_secondary_structure_control.py
python3 Tests/test_mcp_bridge.py
bash Tests/test_iterative_cli_contract.sh
python3 Tests/test_design_cardinality.py
python3 Tests/test_vendor_pipeline.py
swift build
git diff --check
```

The new lifecycle tests are registered in the fast suite, and the monomer
integration tests in the science fixture suite. MCP tests require loopback access;
SwiftPM requires an environment in which its manifest sandbox can start.

## Limits and what was not tested

No real-model predictions, real MPNN calls, GPU optimization, biological
effectiveness comparisons, new reference-cohort thresholds or benchmarks.
Synthetic coordinates and confidence scores only validate software behavior.
No setting was promoted to a scientific default. No weights or existing raw
campaign outputs were changed. No Validation campaign was run.

No desktop form controls for monomer refinement, interactive GUI acceptance,
resident/cycle-wave refinement, power-loss testing, cross-hardware equivalence,
full packaging/release acceptance or full repository test-suite run. No commit
was created. The feature is available in the shared runner and MCP; its ability
to improve real monomer secondary structure remains unmeasured.

## Next

Evaluate monomer effectiveness with a separately declared and audited campaign
before drawing scientific conclusions or promoting any criteria. Add native UI
controls and separately validate resident/cycle-wave stage scheduling if those
entry points are needed.
