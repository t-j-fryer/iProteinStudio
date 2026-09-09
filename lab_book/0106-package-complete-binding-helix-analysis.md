---
entry: 0106
title: Package the complete binding helix-control analysis
date: 2026-09-08
author: Codex
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [protein-binding, secondary-structure, geometry, analysis, figures]
---

## Context

The aCbx binding benchmark in `[[0105-add-target-agnostic-binding-helix-benchmark]]`
was complete but had only a compact Markdown/JSON/CSV summary. The user requested
the same complete output package as the target-free benchmark. No inference,
scientific setting or raw campaign output was changed.

## What was done

Added `Validation/experiments/binder_helix_strength_full_analysis_v1/` with a
reproducible analysis script, tests and usage notes. It verifies the v7 manifest,
stage receipt, frozen experiment/source hashes, 28 audits and every audited raw
path. It replays binder-chain Biotite P-SEA, pLDDT, iPTM, optional ipSAE(min) and
complex pLDDT, exact target-chain identity and geometry directly from coordinates.

The generated directory has exactly the same filename contract as the monomer
`full_analysis_v1`: five SVG/PDF/PNG figure sets, combined PDF, embedded-SVG gallery,
report, full data tables, paired contrasts, integrity/artifact hashes and ZIP.
Binding-specific panels add iPTM and the declared 0.7 hit threshold. Cycle00 is
shown as initialization but excluded from primary endpoints.

## Results

All 23,449 audited raw paths (18,332 unique files), 840 structures and 140 completed
trajectories passed replay; 700 optimization cycles enter the primary endpoint.
Strength 1 lowers mean helicity in all seven engines. Five unadjusted n=10 paired
95% intervals exclude zero; the largest shift is Protenix Mini, −41.4 percentage
points [−56.3, −27.1]. Every paired mean-iPTM interval crosses zero. There are 57
final computational hits.

Geometry replay finds 243 flagged distances in 25 structures/13 trajectories; one
final structure retains two warnings. All remain included under record-only policy.
The integrity report preserves 144 recorded Boltz SVD fallback log lines. Three
tests pass, including exact reproduction of every frozen paired estimate/interval.
All five PNGs were visually inspected. Five SVGs parse, 24 artifact checksums match,
the gallery embeds five figures and the 25-file ZIP passes integrity.

## Decision and rationale

Use the proven monomer output contract for consistent navigation and archiving,
while adapting plots to binding endpoints. Keep iPTM/hit counts as predictor outputs,
not affinity measurements; do not rank engines by uncalibrated scores. Missing
optional metrics remain null rather than being substituted.

## Reproduce

Base commit `37cc95497283025191e7d2067cb35d1af9168d72`, with the recorded dirty
working state. Benchmark manifest SHA-256
`4ba8855fed8f38afe46fb73387b9e9fc73d6a716f814b4d6d21fa4d59e87c391`;
stage receipt SHA-256
`8853fa01eca498828b1514fff476f9ef0b93d163ac07bd58b225c37e864c2088`.
That receipt freezes the Apple M4 Max hardware, all seven engine/checkpoint
inventories and staged files. Analysis SHA-256
`334e3c2271e117b4235b42487bbafcab4eb4bac07f189b306ed38a722d29e755`.

```bash
MPLCONFIGDIR=/private/tmp/binder-helix-full-analysis-mpl /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python Validation/experiments/binder_helix_strength_full_analysis_v1/analyse.py
MPLCONFIGDIR=/private/tmp/binder-helix-full-analysis-mpl /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python -m unittest discover -s Validation/experiments/binder_helix_strength_full_analysis_v1 -p 'test_*.py' -v
```

## Limits and what was not tested

No browser-interaction, wet-lab binding/folding/stability/specificity/toxicity/function,
non-aCbx target, target structure, epitope, multiplicity correction, cross-engine
calibration, comprehensive stereochemistry or speed test was performed. No setting
is promoted. The completed target is a toxin; only the campaign script is reusable
with a separately frozen non-toxin FASTA/MSA.

## Next

Use this as the complete v7 handoff. Repeat a new immutable campaign before
generalizing to a non-toxin target.
