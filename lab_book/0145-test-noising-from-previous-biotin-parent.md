---
entry: 0145
title: Test partial noising directly from a qualified previous biotin parent
date: 2026-09-17
author: GPT-6 Codex
type: experiment
status: complete
machine: Apple M4 Max, 64 GB unified memory
tags: [nise, partial-noising, validation, resident]
---

## Context

User asked to use a previous binder to test the newly coded branch after the
five-start pilot failed before optimization ([[0144-validate-xcode-tests]]).

## What was done

Added a private typed `nise_branch_test` adapter using the regular campaign
configuration, Backend and actual `partial_noising.run_branch`. Extracted argument
parsing without changing normal campaign control flow. The explicit test mode
cannot be mistaken for a normal campaign. It fingerprints imported parent JSON,
PDB, self-consistency reference and atom map, plus the normal code/model assets;
uses the shared broker lock and audited operation replay. No fabricated Phase-0
checkpoints. Experiment scripts/manifest are under
`Validation/experiments/biotin_parent_noising_v1`.

Parent: completed run `nise-C9CCE180-9E41-4BA3-95AE-CB03FBB867FA`, candidate
`c06_t1_n0_s58`; historical score 1.4353053, ligand pLDDT 91.06125,
P(bind) 0.5246928. Recomputed strict parent Cα/ligand RMSD 0.792614/0.948938 Å;
O18/O19 retained SASA fractions 0.7400/0.674419; all nine hotspot contacts pass.
13 residues within 6 Å; mask three (25%, rounded) per proposal.

Plan `plan-3f997fd4df797b01`; job `job-3f997fd4df79`;
managed output `test2/nise_runs/nise-branch-0472093142998daf`.
Two masked predictions, best passing backbone, three repairs, one reserved place;
at most five folds, resident Boltz, empty MSA, unchanged structure/affinity settings
and atom filters. Cycle-2 ligand RMSD is diagnostic, as in the campaign.

## Results

44 NISE tests pass using the managed Boltz Python and runtime root. The first
test attempt omitted NANOHUNTER_ROOT and failed one model-data lookup; rerun with
the correct root passed. `swift build` passes. Its first sandboxed attempt could
not write the standard compiler cache; the authorized retry succeeded after SDK
stat-cache generation. Logs are in [artifacts](artifacts/0145-biotin-parent-noising/).

The real job completed and the independent [output audit](artifacts/0145-biotin-parent-noising/audit.json)
passed: five structure predictions, four affinity evaluations, all12 operation
receipts/hash sets verified. One resident MPS worker (PID73202) survived across
masked folding, affinity, LASErMPNN repair and repair folding/scoring; model load
counts were1 for structure and2 after loading affinity, without further loads.
One documented Boltz `aten::linalg_svd` fallback warning; no unexpected fallback.

| Candidate | Ligand pLDDT | P(bind) | Combined score | Cα / ligand RMSD vs immediate reference (Å) | Outcome |
|---|---:|---:|---:|---:|---|
| Historical parent | 91.0613 | 0.52469 | 1.43531 | 0.793 / 0.949 | Imported; fresh geometry audit passes |
| mask_s0 | 77.6069 | 0.37626 | 1.15233 | 0.657 / 5.198 | Selected intermediate; never a finalist |
| mask_s1 | 57.1969 | — | — | 0.706 / 3.909 | O19 exposure failure; affinity skipped |
| repair_s0 | 77.5150 | 0.39879 | 1.17394 | 0.561 / 18.412 | Passes cycle2; not selected |
| repair_s1 | 83.8194 | 0.33927 | **1.17746** | 0.850 / 1.615 | Selected complete repair |
| repair_s2 | 70.2806 | 0.28129 | 0.98409 | 0.730 / 20.061 | Passes cycle2; not selected |

All three repairs pass current atom criteria and backbone RMSD. Only repair_s1
would also pass a2.5 Å ligand gate against its immediate reference. Both masked
predictions would fail that gate if applied at this step; cycle2 deliberately
does not apply it. The selected repair remains4.988 Å from the **original** parent
ligand pose (backbone0.724 Å): passing against the masked intermediate does not
mean preserving the original pose. This is sequence masking and global refolding,
not spatially restrained coordinate diffusion.

The selected score is below the historical parent's score; no improvement is
demonstrated. No paired baseline refold, performance measurement or default
promotion. The optional branch works end to end under the recorded cycle2 policy;
this is not evidence of binding or of later-cycle branch survival.

## Decision and rationale

Use a qualified existing parent to isolate mask→fold→filter→affinity→repair→fold
from initial-funnel attrition. Keep the previous failed pilot and held full plan
unchanged; successful software execution alone is insufficient acceptance.

## Reproduce

See the experiment README and saved plan/launch under
`Validation/output/biotin_parent_noising_v1`. Starting commit
`92bdae1a1c4b547e6f3ab4bd851ffa6bea55c3e8` plus this entry's changes;
immutable plan fingerprints the exact executed working-tree snapshot.

## Limits and what was not tested

Single parent and reduced proposal counts; no ordinary two-parent pool, beam
mixing, full32+32 sampling, efficacy comparison, new cancellation/restart or
memory-soak test. Initial funnel is deliberately outside this test. No app/DMG
replacement or full campaign launch is part of this bounded test.

## Next

Keep the optional feature experimental. If assessing usefulness, test more parents
with the later-cycle ligand gate active and compare against matched ordinary MPNN
sampling. The large campaign remains held; this bounded test does not silently
replace the previous full-funnel/beam acceptance condition or launch more work.
