---
entry: 0141
title: Compare Studio atom accessibility with reported alpha-hull exposure
date: 2026-09-17
author: Codex
type: audit
status: complete
machine: Source inspection only
tags: [nise, exposure, geometry]
---

## Context

The user reported that another run used a protein Cα alpha hull, alpha 9.0 and
five rays, throughout the run, and asked how Studio compares.

## What was done

Read `atom_geometry.py`, `runtime.py`, `nise_run.py` and `partial_noising.py` in the
shipped NISE source. Searched local NanoHunter and iProteinHunter-beta source for
the reported alpha-hull/ray implementation; no matching implementation was located.
Checked the primary [FreeSASA paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC4776673/)
for the general interpretation of Shrake–Rupley atom-surface accessibility.

## Results

No measurements. Studio uses RDKit FreeSASA, Shrake–Rupley, heavy atoms including
protein sidechains, element-specific van der Waals radii and a 1.4 Å probe.
For each selected exposed ligand atom it measures complex SASA divided by
isolated-ligand SASA, retaining the exact ligand coordinates. The proposed biotin
threshold is 0.5 for each selected atom individually; isolated area ≤0.1 Å² fails.
With the proposed selective-affinity settings, the check runs during initial generation/refinement/gate/expansion, ordinary
optimisation, masked intermediates and repairs. Selective affinity follows the
geometry check for eligible candidates.

## Decision and rationale

These methods are not equivalent. The reported Cα hull describes a coarse protein
envelope; Studio quantifies local atom-surface occlusion. Alpha 9.0 cannot be
equated with either Studio's 1.4 Å probe or its separate 6 Å contact cutoff.
Without the other script, the five-ray voting rule and alpha convention remain
unknown; do not describe the rays as validated linker exit paths. Neither an
ordering of strictness nor preservation of historical survivors is established.
Local SASA does not explicitly test connectivity to bulk solvent or clearance for
an attached protein. No settings or implementation changed.

## Reproduce

Read the four NISE files above, particularly `atom_geometry.measure`,
`runtime.Backend.check_atom_requirements`, `nise_run.evaluate_candidates`, and
the initial-generation and partial-noising call sites.

## Limits and what was not tested

No other-run script supplied, no matched-structure comparison, no model inference,
no runtime tests/build for this read-only source audit, and no campaign launch.

## Next

Obtain the other implementation before claiming equivalent filtering or porting
its alpha-hull settings. A paired saved-structure comparison could quantify which
candidates pass each filter without rerunning prediction.
