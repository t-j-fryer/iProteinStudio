---
entry: 0147
title: Remove partial noising from the proposed biotin campaign
date: 2026-09-17
author: Codex
type: decision
status: complete
machine: Local development Mac; configuration calculation only
tags: [nise, biotin, settings]
---

## Context

Following0146, the user decided to drop partial noising and asked what settings
would now apply. Return to the originally requested ordinary beam of three,
32 proposals per parent and64 total proposals per seed in optimization cycle1.

## What was done

Created a new [draft request](artifacts/0147-biotin-without-noising/draft_request.json)
from the previously reviewed full biotin request. The only scientific setting
changed is `partial_noising: false`; `beam: 3` now means three ordinary sampling
parents with no reserved branch. Inactive noise controls remain serialized by the
typed contract but do not perform work. Preserved existing immutable plans and raw
outputs; no broker plan, job, app update or new campaign was launched.

## Results

Normalized the draft through the actual request contract and calculated its
[budget](artifacts/0147-biotin-without-noising/budget.json). Asserted that disabling
partial noising is the sole difference from the previous full request.

Settings: Protein Hunter initial generation,1000 starts,65–150 residues,50% initial
X tokens; two refinement rounds with3 sequences per lineage and first-round score
gate0.80; unrestrained gate3 sequences per lineage with Cα RMSD<2 Å; expansion5 per
gate survivor; up to8 seeds from distinct initial lineages. Noising disabled during
optimization does not disable the initial X-token backbone generator.

Optimization: cycle1 uses64 proposals per seed; later cycles use up to3 parents ×32
=96 proposals per trajectory, advancing the top3 passing candidates pooled within
each trajectory. At most30 cycles and patience4, with improvement>0.01 needed to
reset patience. Best-so-far designs preserved. No adaptive sampling, rollback or
rescue. LASErMPNN, resident Boltz2, NESSO off, apo analysis off, empty MSA, seed0.

Filters/scoring unchanged: nine reviewed biotin head hotspots within6 Å; terminal
O18/O19 each retain>=50% isolated-ligand SASA; optimization Cα RMSD<2.5 Å and ligand
RMSD<2.5 Å from cycle3. Geometry precedes selective affinity, affinity batch8;
rank ligand pLDDT/100+P(bind). Initial generation and unrestrained gate omit affinity.

Arithmetic ceilings:512 first-cycle folds across8 trajectories;768 later-cycle
folds;22,784 optimization folds;25,000 initial-stage folds;47,784 total. These are
maximum structure-prediction counts, not runtime or affinity-head counts. Attrition
and patience reduce actual work. No performance measurements.

## Decision and rationale

Restore ordinary three-parent search because the user's earlier reduction to two
ordinary parents was specifically to make room for partial noising. All parents
now participate normally. Keep prior atom criteria and filtering decisions.

## Reproduce

Load the draft request with `contract.normalize`, then pass its `request` field
to `contract.prediction_budget`. Source contract lives under
`Sources/iProteinStudio/Resources/pipeline/scripts/nise`.

## Limits and what was not tested

Configuration validation and arithmetic only. No neural inference, new smoke run,
full campaign, software modification or build. Previous plans still retain their
original settings and must not be resumed as this revised request.

Clarification after the user's follow-up: inspected `nise_lib.self_consistency`
and the optimization call sites. The filter is global chain-A Cα RMSD after a
rigid Kabsch alignment, against the immediate parent supplied to MPNN. It is a
hard eligibility gate before affinity, not an extra ranking term or a coordinate
restraint during folding. It permits cumulative drift across accepted cycles;
it does not enforce 2.5 Å to the initial seed or a per-residue displacement limit.
Global agreement does not establish local pocket accuracy or experimental binding.
The original RFdiffusion study uses a related 2 Å global backbone consistency
criterion (https://www.nature.com/articles/s41586-023-06415-8); that supports the
general validation concept, not optimality of this NISE cutoff. Keeping 2.5 Å is
a provisional local-search choice. No cutoff changed or new inference performed.

## Next

Use the new draft for any subsequent preflight; do not submit the old noising plan.
