---
entry: 0022
title: Package the complete binding helix-control analysis
date: 2026-09-08
author: Codex
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [protein-binding, secondary-structure, geometry, analysis, figures]
---

## Context

The completed v7 aCbx campaign lacked the complete visual/data package used by the
target-free v3 benchmark. The user requested matching outputs. This is retrospective
analysis only; no prediction or raw campaign artifact changed.

## What was done

Created `Validation/experiments/binder_helix_strength_full_analysis_v1/`. It verifies
manifest/stage/source/audit/raw identities, then replays Biotite P-SEA, binder/target
identity, pLDDT, required iPTM, optional scores and geometry. It emits the same 26
filenames as the monomer full analysis: five figure triplets, combined PDF, gallery,
report, full CSV/JSON tables, hashes and ZIP. Figures use Arial, black axes/text,
inward ticks, no grids, transparent SVGs and outlined bars. Trajectories—not cycles
or residues—are statistical units; cycle00 is excluded from primary endpoints.

## Results

All 23,449 raw-path checks (18,332 unique files), 840 complexes, 140 trajectories
and 700 optimization cycles passed replay. Strength-1 helicity means are lower for
all seven engines; five unadjusted n=10 paired intervals exclude zero. The largest
change is Protenix Mini, −41.4 percentage points [−56.3, −27.1]. All seven paired
mean-iPTM intervals cross zero; 57 final outputs exceed iPTM 0.7.

Geometry replay records 243 flagged distances in 25 structures/13 trajectories and
two warnings in one final structure. These remain included. Three tests reproduce
all frozen paired results and enforce the output contract. Five PNGs were visually
inspected; SVG, artifact-hash, gallery-embedding and ZIP checks pass.

## Decision and rationale

Match the validated output contract exactly while using binding-relevant panels.
Do not impute optional metrics, rank engines by uncalibrated confidence, or interpret
iPTM as measured affinity.

## Reproduce

Base commit `37cc95497283025191e7d2067cb35d1af9168d72`. Manifest SHA-256
`4ba8855fed8f38afe46fb73387b9e9fc73d6a716f814b4d6d21fa4d59e87c391`;
stage receipt SHA-256
`8853fa01eca498828b1514fff476f9ef0b93d163ac07bd58b225c37e864c2088`.
The receipt freezes the exact hardware and engine/checkpoint inventory. Analysis
SHA-256 `334e3c2271e117b4235b42487bbafcab4eb4bac07f189b306ed38a722d29e755`.

```bash
MPLCONFIGDIR=/private/tmp/binder-helix-full-analysis-mpl /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python Validation/experiments/binder_helix_strength_full_analysis_v1/analyse.py
MPLCONFIGDIR=/private/tmp/binder-helix-full-analysis-mpl /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python -m unittest discover -s Validation/experiments/binder_helix_strength_full_analysis_v1 -p 'test_*.py' -v
```

## Limits and what was not tested

No browser interaction, wet-lab assay, non-aCbx target, target structure, epitope,
multiplicity correction, cross-engine calibration, comprehensive stereochemistry or
speed test was performed. The 144 recorded Boltz SVD fallback lines remain disclosed.
No setting is promoted.

## Next

Use this package as the complete v7 record. A non-toxin target requires a new
immutable campaign with its own exact FASTA/MSA.
