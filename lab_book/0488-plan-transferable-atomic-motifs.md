---
entry: 0488
title: Plan transferable atomic motif scaffolding and search
date: 2026-10-21
author: Codex
type: audit
status: complete
machine: CPU-only input audit; no model inference or performance measurements
tags: [motif-scaffolding, rfd3, ligandmpnn, lasermpnn, search, ame]
---

## Context

User requested exact Artios benchmark atomic motifs/ligands and a plan to make
RFdiffusion3 motif scaffolding transferable to template-capable iterative engines,
with motif/ligand geometry driving greedy/beam search and a LigandMPNN versus
LASErMPNN comparison. Follows [0487](0487-review-artios-enzyme-benchmarks.md).

## What was done

- Located the original AME-41 release in RosettaCommons/RFdiffusion2 at
  `d365cbf4db3958814a9f8e4f6f94fa309dfebc2b`. Preserved 41 PDBs, `mcsa_41.json`,
  two configuration files and BSD license in `artifacts/0488-ame-motif-policy/`.
- Ran a deterministic input audit against source Git blob hashes; extracted all
  protein conditioning atoms, ligand instances, coordinates and both original
  ligand mask policies into JSON and Markdown inventories. No shell-like input
  specification was executed.
- Inspected current connected workflow guides/catalog plus canonical/staged
  source, predictor template features and both sequence-designer adapters.
- Inspected Foundry production tree at
  `d078b24d6d0e6f8607e9a0311128f4a897f83953`. Its AME config references separately
  supplied benchmark data. No exact Artios-38 manifest was found through public
  paper/landing-page/repository searches. Optional RCSB plugin is not installed.
- Wrote [implementation and comparison plan](../docs/MOTIF_SCAFFOLDING_PLAN.md).
  Existing production code, pending user edits and running campaigns unchanged.

## Results

No inference/performance measurements. CPU data audit: 44 source files matched
Git blob hashes; 41 cases, 172 motif residues, 524 selected protein atoms,
80 ligand instances, 56 distinct component codes, 30 multi-ligand cases.
All selected atoms resolve to finite original coordinates. This verifies data
integrity, not physical chemistry, engine compatibility or scientific success.

The base AME specification records partially fixed ligand atoms; its fixedligand
configuration clears the partial mask and disables ligand flexibility. Both are
retained rather than silently conflated. Artios' three exclusions, input changes,
exact all-atom scoring alignment and contradictory counts remain unresolved.

Confirmed template-guide candidates: Boltz-2, Protenix v2, IntelliFold v2
Flash/full. They provide protein geometry evidence, not arbitrary catalytic-atom
locks. Protenix Constraint's inspected inference substructure parser is a TODO;
do not claim its model name implies available motif coordinates. Current general
template alignment also does not guarantee correct mappings across changing
scaffold sequence/discontinuous fragments.

Current LASErMPNN RFD3 wrapper prepares all residues as designable and omits
`--fix_beta`; its preparation helper assumes one ligand/SMILES and renames atoms.
Those contracts need extension before enzyme-motif comparisons. LigandMPNN
already exposes fixed-residue mappings, with side-chain-context policy still to
qualify. Original raw files were not altered during inventory generation.

## Decision and rationale

Use one versioned motif/chemistry/mapping bundle from generation through every
cycle. Generalize optional targets and multi-ligand inputs, then evaluate geometry
against a frozen reference. Keep generation constraints, template guidance and
independent measurement distinct. Fail unsupported requested conditioning.

Propose fold-quality gates and minimization of the worst normalized motif/ligand
error, `max(motif_rmsd/2.5, max_ligand_centroid_displacement/3)`, with a separately
registered source-functional-atom guard and pose/contact diagnostics. Use
untemplated search checks, followed by held-out model-family evaluation. This
objective is a proposal, not a validated setting or exact Artios implementation.

Cross four search policies with two sequence designers on shared RFD3 roots and
equal total fold budgets; start with one cycling predictor. Defer extra-engine and
templating ablations until the base comparison works. No adaptive setting is
promoted from existing binder results.

## Reproduce

```bash
python3 lab_book/artifacts/0488-ame-motif-policy/audit_inputs.py
```

This verifies original Git hashes and deterministically regenerates
`inventory.json`, `INVENTORY.md` and `audit.json`. Source URLs/revision and each
file's original Git hash are in `source_manifest.json`; SHA-256 values are in
`audit.json`. Python standard library only; no model or network access needed.

Sources: RFdiffusion2 `rf_diffusion/benchmark/mcsa_41.json`,
`input/mcsa_41/`, `configs/enzyme_bench_n41{,_fixedligand}.yaml`; Foundry
`models/rfd3/docs/input.md` and `configs/datasets/val/mcsa_41.yaml`; local
`docs/PREDICTION_TEMPLATES.md`, `scripts/lasermpnn_prepare_input.py`,
`rfd3_overlay/scripts/run_{mpnn,lasermpnn}.py`, ProtenixConstraint
`constraint_featurizer.py` and current connected pipeline catalog.

## Limits and what was not tested

No new generation, sequence sampling, predictor inference, hardware benchmark,
production-code integration, run plan/job, Swift build or commit. No laboratory
experiment. CCD bonds, stereochemistry, protonation states and multi-engine atom
mappings still need qualification. Selected-atom resolution does not certify
catalysis. No exact Artios-38 reproduction claim, no unverified exclusions, and
no DNA/RNA checkpoint or new modality enabled.

## Next

Implement bundle/metric fixtures and generalized planner first, then sequence
mask/multi-ligand adapters and explicit motif-template mappings. Complete managed
end-to-end smoke runs before a preregistered Validation campaign, with its own
manifest, immutable outputs, audit and Validation Lab Book entry.
