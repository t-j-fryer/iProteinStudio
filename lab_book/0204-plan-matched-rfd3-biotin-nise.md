---
entry: 0204
title: Propose matched RFdiffusion3 initialization for biotin NISE
date: 2026-09-27
author: Codex
type: decision
status: complete
machine: Source and saved-request review; no inference
tags: [rfd3, nise, biotin, planning]
---

## Context

User requests settings for a new 1,000-backbone RFdiffusion3 campaign as similar
as possible to Boltz NISE nise-3ea5fa63a1effece. This is a recommendation, not
authorization to launch. Follows 0203.

## What was done

Read the saved nise_config.json, NISE workflow guide, rfd3_initial.py, contract.py,
campaign.py, MCP desktop.py, RFD3 design_from_yaml.py allocation logic and entries
0181, 0185, 0199, 0203. Checked official Foundry input documentation:
https://github.com/RosettaCommons/foundry/blob/production/models/rfd3/docs/input.md

## Results

No measurements or new model evaluations. Adapter uses 200 diffusion steps,
2 recycles, BF16, batch size 8, two shape queues per bin, one ligand conformer,
fixed ligand atoms and COM initialization. It translates atom identities through
the shared standardized SMILES map, audits exact output counts and atom sets,
and resumes audited batches. In biotin-carboxamide-v1 it excludes terminal
oxygen exposure conditioning. No explicit buried or donor/acceptor conditioning
is added by this adapter. Geometry filtering remains shared downstream.

## Decision and rationale

Recommend 1,000 starts, explicit stereospecific biotin identical to the saved
campaign, same nine hotspots, and the same carboxamide exit policy accepting open
and restricted while rejecting blocked/unresolved. Do not restore old 50% terminal
oxygen SASA or broader tail exposure conditioning. Recommend 20 evenly spaced
length bins from 65 to 150 (50 designs each): supported request bound, closer
coverage than default five bins, but not the original exact length histogram.
This is a proposed experiment setting, not a default promotion. More shapes may
cost extra compilation time; no performance advantage is asserted.

Keep Boltz objective ligand pLDDT/100 + P(bind), LASErMPNN, two refinement rounds
of three proposals, first-round 0.80 gate, unconstrained gate three proposals and
2-A C-alpha self-consistency, expansion five per survivor, eight distinct seed
lineages. Optimisation: first cycle 64 per seed, later 32 per parent and beam 3,
30-cycle cap, patience 4, improvement threshold 0.01, existing 2.5-A protein and
ligand self-consistency settings (ligand from cycle 3). Geometry before selective
affinity, batch 8. No NESSO/PSICHIC, adaptive sampling, partial noising or apo stage.

Use the validated EMA weight selection and current atom-export/empty-selection
repairs, not arbitrary newer weights. Retain current Boltz physical guidance
and stage-specific pocket-restraint policy downstream. Native RFD3 hotspot
conditioning is not identical to Boltz forced pocket potentials; common postfold
filters make comparison more interpretable, not perfectly matched.

## Reproduce

Saved comparator:
`/Users/thomasfryer/.iproteinstudio/projects/test2/nise_runs/nise-3ea5fa63a1effece/nise_config.json`.
Implementation: `Sources/iProteinStudio/Resources/pipeline/scripts/nise/rfd3_initial.py`.

## Limits and what was not tested

No inference, launch, new immutable execution plan, source changes, tests, runtime
detection or benchmark. Fixed ligand conformer differs from Boltz's sampled ligand
coordinates; initial RFD3 backbone-only geometry also differs from folded
sequence-bearing structures. Compare filtering again after first common MPNN/
Boltz stage. Do not assume 754 initial survivors as in the existing campaign.
Fresh MCP NISE plans do not currently add --resident-workers 2; this is wired to
the explicit continuation descriptor. Matching stage-batched two-worker execution
requires a supported, recorded and tested path before launch, not a request-field
assumption or bypass of the broker.

## Next

If approved for execution, detect runtimes, qualify 1-5 backbones end to end with
these exact stereochemistry/atom/exit settings, and record a new immutable managed
plan. Track counts after each filter, matched downstream score distributions,
independent lineages and separate generation/folding/affinity time. No duration or
efficacy prediction is justified by the existing one-backbone launch checks.

## Follow-up: generator atom conditioning

User intends 1,000 starts but asks to settle conditioning before launch. Recommend
the existing nine core/head hotspots only; no explicit buried, partially buried
or exposed RASA selections for this matched comparison. Leave the valerate tail
and terminal carboxyl group without hotspot/RASA labels, while retaining the hard
postgeneration linker-exit check and repeating it after folding. Unspecified RASA
does not mean exposed. The upstream input specification describes hotspots as
typically within 4.5 A of designed heavy atoms; this is learned conditioning, not
our 6-A acceptance threshold or a full-burial requirement. Exposed conditioning
could be a separate generation-bias experiment but is not evidence of an open
linker path and has not been validated for these starts. Current adapter explicitly
removes terminal-oxygen exposure labels in carboxamide mode. No job launched or
conditioning changed during this clarification.

## Revised objective: best justified method-specific conditioning

User clarified that useful generation takes priority over exact method matching.
The recommendation below supersedes the minimal-conditioning recommendation above;
it is a chemically motivated proposal, not a measured optimum or implemented change.

Retain the nine head hotspots. Add buried conditioning on the nonpolar ring
subset C31,S20,C29,C32,C30. Label the ureido oxygen O17 as an H-bond acceptor and
N23,N24 as donors; leave those polar atoms without an explicit buried RASA label.
Select only terminal hydroxyl O19 as exposed; terminal carbonyl O18, carboxyl
carbon C22 and hydrocarbon tail remain without RASA/hotspot conditioning. Roles
are verified against the saved standardized neutral-biotin graph, not transferable
atom numbering. O19 exposure is a proxy for the attachment direction, not a linker
fit guarantee or an assertion that the oxygen persists in the conjugate. Repeat
the unchanged carboxamide exit geometry check after generation and later folding.
Do not impose a hard terminal SASA cutoff or require the whole tail to be exposed.

Reviewed official input.md and input_parsing.py plus the saved ligand atom map
and local biotin_exit.roles. Upstream independently encodes hotspot, H-bond and
RASA features; buried/exposed sets must be disjoint. Retain the existing RASA
merge repair and audit final fixture annotations before use. Current NISE adapter
needs explicit generator-specific selections to support this proposal: it currently
strips terminal oxygen exposure and forwards neither burial nor H-bond selections.
Generation conditioning must be separate from postprediction eligibility settings.
No source implementation, launch, test or performance measurement in this follow-up.
