---
entry: 0137
title: Separate NISE sampling budgets and add optional ligand-local masking
date: 2026-09-16
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 64 GB unified memory; software checks only
tags: [nise, boltz, lasermpnn, nesso, ui, checkpointing]
---

## Context

After [0135](0135-fluorescein-nise-adaptive-retrospective.md), the user chose to
leave adaptive sampling off and requested 32 proposals per parent, beam three,
but 64 proposals in the first optimisation cycle. They also requested an optional
ligand-local X-token branch. The user confirmed one extra branch from the best
current parent: masked folds → best passing backbone → MPNN redesigns → reserved
next-beam place. The other two places come from the normal MPNN pool.

## What was done

Policy v3 adds `first_cycle_seqs=64`, sets `nise_seqs=32`, preserves beam three,
and keeps 1,000 starts / 30 maximum cycles / four-cycle patience. Swift, Python,
MCP schema/catalog, budgeting, CLI handoff, migration and documentation agree.
Saved v1/v2 requests retain their original shared first/later count. Disabled
new fields do not invalidate historical frozen configurations. Adaptive remains
off and cannot be combined with partial noising; the existing improvement
tolerance was not changed.

Added `partial_noising.py`, with the option off by default. From cycle 2, take
the highest-scoring current parent in each trajectory. Identify sequence-indexed
residues with any protein heavy atom within 6 Å of a ligand heavy atom; mask a
random 25% (nearest integer, at least one for a nonempty neighbourhood). Save
exact positions, residue IDs, parent hash and 32 distinct prediction seeds.

All 32 masked predictions go directly to Boltz. Apply the same geometry and atom
requirements, and rank passing intermediates with Boltz ligand pLDDT/100 + P(bind).
Selective affinity stays geometry-first. The masked score is explicitly an
experimental intermediate-selection heuristic. It never becomes a final score,
beam parent, best-so-far design or apo-analysis candidate.

Create an inverse-folding input copy converting only binder-chain UNK names to
ALA placeholders, reusing the existing upstream preparation/design workflow.
Generate 32 complete LASErMPNN sequences from the chosen masked backbone, screen
with NESSO if enabled, then fold and score with Boltz. Reserve one beam place for
the best passing repair and choose two normal candidates from the ordinary pool.
An empty/rejected branch leaves its reserved place empty and records why.
Normal sampling still uses every current parent. Both Protein Hunter and RFD3
initial-backbone routes share this implementation.

Noising-specific prediction seeds travel through the existing resident worker;
structure and affinity requests preserve the same override. Other requests keep
the worker's configured seed, without model reloads. Saved masks, MPNN sampling,
structure/affinity operations, repair inputs and branch/beam provenance replay
after interruption. Exposed typed controls, explanatory costs and intermediate
labels in the native UI and MCP result overview; added the suite to Tests/run.py.

## Results

**No performance or scientific-efficacy measurements — implementation only.**
The following are arithmetic upper bounds per trajectory, not measured timings:

| Configuration | Cycle 1 Boltz predictions | Later-cycle Boltz predictions |
|---|---:|---:|
| Default fixed sampling | 64 | 3 × 32 = 96 |
| Optional noising, no NESSO | 64 | 96 normal + 32 masked + 32 repair = 160 |
| Noising with NESSO shortlist 16 | 16 | 16 normal + 32 masked + 16 repair = 64 |

Software validation: 41 NISE tests and 18 NESSO tests passed. The NISE suite
includes four generator/screening combinations, interruption after masked
selection, complete replay with zero new model operations, reserved selection
even with a lower-scoring repaired winner, rejected-branch behavior, heavy-atom
mapping (including sidechain and hydrogen controls), mask/repair corruption
checks, per-request seed isolation, apo exclusion, frozen-config migration and
MCP snapshot/result contracts. Swift request/migration and results harnesses pass;
`swift build --disable-sandbox --skip-update` passes. Build, test logs and exact
source hashes are archived in `artifacts/0137-nise-partial-noising/`.

## Decision and rationale

This is **sequence masking, not coordinate partial diffusion**. Boltz refolds the
whole chain; residues outside the mask are not spatially frozen, and the later
MPNN step can redesign the whole binder. Keep existing RMSD and Bind/Expose
checks rather than implying preservation of the outside geometry. Repair folds
are compared with their selected masked backbone; masking folds are compared
with the original current parent. There is no rollback/rescue, no extra Phase-0
stage and no hidden inference in the first cycle.

6 Å and 25% are adjustable experimental starting choices, not promoted validated
settings. The aim is a relatively local perturbation, with 8 Å available for a
broader neighbourhood. The LigandMPNN primary paper uses a 5 Å sidechain-contact
cutoff for near-ligand recovery and discusses roughly 10 Å ligand context. This
motivates considering local shells but does **not** validate the selected X-mask
radius/fraction or affinity on masked proteins. The existing LASErMPNN 10 Å Cα
temperature shell remains a separate parameter. [Primary paper](https://www.ipd.uw.edu/publication-pdfs/331/b896bbdf83798df6853c60bf2f2a0928/s41592-025-02626-1-3.pdf).

Compared with substituting a masked protein directly into the beam, complete
MPNN redesign and refolding ensure all final sequences contain ordinary amino
acids and receive the normal checks. Masked scores remain provisional. Compared
with allowing all candidates to compete for all three slots, a reserved slot
implements the user's explicit request to retain one branch descendant. Failed
branches cannot force an invalid survivor into the beam.

## Reproduce

From the canonical repository:

```bash
NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  -m unittest discover -s Tests -p 'test_nise*.py'
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python Tests/test_nesso_screen.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules \
  swift build --disable-sandbox --skip-update
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules swiftc \
  -module-cache-path /private/tmp/iproteinstudio-modules -parse-as-library \
  Sources/iProteinStudio/Models/NISERequest.swift \
  Sources/iProteinStudio/Models/WorkspaceOrganization.swift \
  Sources/iProteinStudio/Models/Project.swift Tests/NISERequestContractHarness.swift \
  -o /tmp/iproteinstudio-nise-v3-contract
/tmp/iproteinstudio-nise-v3-contract
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules swiftc \
  -module-cache-path /private/tmp/iproteinstudio-modules -parse-as-library \
  Tests/PredictionResultsContractHarness.swift Sources/iProteinStudio/Models/RunResult.swift \
  Sources/iProteinStudio/Core/Results/RunResultsLoader.swift -o /tmp/iproteinstudio-nise-v3-results
/tmp/iproteinstudio-nise-v3-results
```

See [NISE documentation](../docs/NISE.md#optional-ligand-local-x-token-noising).

## Limits and what was not tested

No new model inference, ligand campaign, experimental binding measurement,
partial-noising efficacy comparison, GPU timing, long memory soak or interactive
GUI run. The fixtures verify orchestration and contracts, not model behavior on
masked proteins. NESSO efficacy and masked Boltz affinity interpretation remain
unvalidated. No app installation, DMG, commit or GitHub push. Existing running
campaigns and unrelated local changes remain untouched. Live runs continue with
their frozen code snapshots. No weights copied or redistributed.

## Next

Use the governed bridge for a bounded real-model pilot before broad campaigns.
Measure pass rates, actual coordinate drift inside/outside the mask, complete
repair quality and extra compute against ordinary fixed MPNN at equal total
budget. Record the manifest/audit and both Lab Books before promoting any noising
settings or claiming a benefit. Keep the option off until deliberately selected.
