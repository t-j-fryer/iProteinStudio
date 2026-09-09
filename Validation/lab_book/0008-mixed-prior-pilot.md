---
entry: 0008
title: Test mixed anti-helix and beta sequence priors at two strengths
date: 2026-09-04
author: gpt-6
type: experiment
status: submitted
tags: [secondary-structure, mixed, beta-sheet, anti-helix]
---

## Hypothesis and controls

The user requested a better beta-enrichment approach and a mixed anti-helix/beta
trial. The completed comparison suggests anti-helix alone increases coil while
the beta prior changes sequence composition without reliably imposing sheet
geometry. Mixing may help, but global anti-helix also opposes E/K/Q encouraged
by the beta polar-face prior. Stronger is not automatically better.

Declare four pilot trajectories: anti-helix 0.25 or 0.50 within mixed mode, each
with seed-only and sustained scope. Beta/composition/pattern/turn strengths remain
0.50. Identical-start pairs isolate sustained pressure. All other scientific
settings match the prior aCbx/90-aa/Boltz/SolubleMPNN campaign: 5 optimized cycles,
fixed seeds, required pinned target MSA and no independent post-prediction.

## Provenance and execution

Use `experiments/secondary_structure_mixed_v1/campaign.py`. It verifies that the
managed scientific runner/helper match the prior campaign hashes and uses the
same planning implementation through the shipped bridge. Workflow guide and
system detection were called; Boltz and MPNN were reported ready. Declare
immutable plans before submission, and save current git/dirty-tree state, runtime
hashes, target-template/MSA checksums and job IDs under the ignored pilot output.
Hardware is the same M4 Max / 64 GB as the previous campaign; no speed claim.

## Submitted jobs

- mixed_a025_seed_only: `job-00cbe4524ea5`
- mixed_a025_sustained: `job-f016478ac89a`
- mixed_a050_seed_only: `job-373cb38a0fa0`
- mixed_a050_sustained: `job-0e3ab3ba07e2`

All plans were reviewed before submission. The first job was running and the
others queued at the initial status check. The launch manifest records current
source and runtime fingerprints. Mechanistic analysis and literature sources
are in project Lab Book 0090. No mixed results are claimed yet.

## Evaluation and limitations

Audit 24 expected structures with matching sequences, finite coordinates and
confidence records. Confirm identical cycle-00 sequences within each strength.
Assign binder P-SEA from coordinates. Exclude cycle 00 from design endpoints.
Compare sheet, helix, coil, binder pLDDT, iPTM and ipSAE. No default promotion.

Only one trajectory per arm: this is a wiring/feasibility pilot, not an efficacy
comparison. No full cohort, alternate backbone method, independent confirmation,
experimental binding/solubility or speed measurement is authorized by this pilot
declaration. Larger comparisons require a separately declared manifest.
