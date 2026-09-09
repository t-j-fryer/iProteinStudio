---
entry: 0020
title: Analyse the complete cross-engine helix-strength benchmark
date: 2026-09-07
author: Codex
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [monomer, secondary-structure, geometry, analysis, figures]
---

## Context

The user requested analysis of all runs and aesthetic figures for the fresh, geometry-record-only benchmark. The completed v3 study covers strengths0,0.5,1 across seven installed predictor variants, 90-aa monomers, ten trajectories and five optimization cycles each. Superseded v1/v2 raw runs are preserved but excluded from this matched study. No scientific execution, engine settings or application code was changed for this analysis.

## What was done

Created `Validation/experiments/helix_strength_full_analysis_v1/analyse.py` and statistical-unit tests. Rechecked all42 cohort audits against manifest/stage identity, frozen experiment/source hashes and29,814 recorded raw paths (24,870 unique files). Replayed coordinate P-SEA, sequence/length, per-residue confidence and geometry diagnostics for all1,260 structures, and verified primary trajectory means. Used frozen output/code rather than requiring an unchanged live runtime after study completion.

Produced five figure sets (SVG/PDF/PNG), combined five-page PDF, standalone embedded-SVG HTML gallery, complete Markdown report, per-structure and per-trajectory CSVs, summary/geometry tables, all84 metric/contrast estimates, provenance hashes and a portable ZIP. Figures use Arial, black axes/text, inward ticks, transparent SVG backgrounds and black bar outlines. All210 trajectories appear in the distributions; paired uncertainty uses trajectories, never cycles/residues, as replicates. Primary endpoint excludes cycle00.

## Results

All210/210 trajectories completed;1,050/1,050 optimization cycles plus210 initializations. Zero failed trajectories. Strength1 lowers mean helicity by11.9–41.2 percentage points across engines; unadjusted paired95% bootstrap intervals exclude zero in six of seven engines. Sheet gains are positive in all seven sample means, with intervals above zero for IntelliFold Flash/full and Protenix Constraint. No multiplicity adjustment; findings are exploratory.

Protenix Mini at1: mean confidence83.4→57.3 (paired−26.0;95% interval[−30.1,−22.0]); mean coil21.5%→52.1%. Protenix Constraint at0.5: helix41.4%→17.0%, sheet21.8%→38.1%, mean confidence86.0→85.3; additional sheet benefit at1 is not established. IntelliFold full at1: mean sheet17.5%→41.4%, final confidence92.1→91.1. OpenFold sample means are non-monotonic, with wide intervals.

Nine atom-pair distance violations occur in four structures/four trajectories (two Boltz initializations and two Protenix Mini cycle03 predictions). Each is absent in the next cycle; no final structure has a flagged violation. These results support preserving opportunities for recovery; they do not prove all coordinate defects are harmless or guarantee recovery.

## Decision and rationale

Initialization-only helix-kill provides a persistent control signal, with an engine-dependent balance of helix, sheet, coil and confidence. No universal dose, runtime default or experimental validity claim is promoted. This campaign does not retest every retired lever and therefore cannot independently establish comparative superiority to all former controls. Confidence scales are not assumed calibrated across engines; OpenFold retains its recorded X-substitution policy.

## Reproduce

Original study commit:37cc95497283025191e7d2067cb35d1af9168d72 plus frozen working changes. Manifest SHA256:`aba3a91b42ec6d48231c9e68c92e20e8288bf7058659b7c299d2d0d4dffc3057`. Exact native model/checkpoint fingerprints, masks, seed schemes, MSA policy (empty; no alignment checksum), hardware and scientific requests remain in the original manifest/stage receipt/plans. Report methods state ten paired seeds,10,000 bootstrap draws, seed906026 and no multiplicity adjustment.

```bash
MPLCONFIGDIR=/private/tmp/helix-full-analysis-mpl /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python Validation/experiments/helix_strength_full_analysis_v1/analyse.py
MPLCONFIGDIR=/private/tmp/helix-full-analysis-mpl /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python -m unittest discover -s Validation/experiments/helix_strength_full_analysis_v1 -p test_analysis.py -v
```

## Validation and limits

Three tests passed: known paired difference, refusal to bootstrap50 repeated cycles as independent samples, and reproduction of all84 original paired estimates/intervals. All five PNGs were visually inspected; overview/header spacing was refined. SVG XML, five PDF pages, archive integrity and every exported artifact checksum passed. No full browser interaction test; standalone gallery uses embedded SVG images. No wet-lab folding/stability/function validation, no common calibration of predictor confidence, no comprehensive stereochemical assessment, no speed claims and no setting promotion. Only the declared C–N and Cα–Cα distance screen is measured.

## Outputs

`Validation/output/helix_strength_all_engines_v3/analysis/full_analysis_v1/`: `REPORT.md`, `GALLERY.html`, `FIGURES.pdf`, `helix_control_complete.zip`, per-figure SVG/PDF/PNG and full numerical data. Every raw output is unchanged. Analysis script SHA256:`e574bb99f93bbd9692a5475577b4a78e394a4b3397fb8f3805f07dddacfdfaa1`.

## Next

Use within-engine effects and uncertainty to select settings for subsequent independent validation; keep geometry diagnostics without automatic intermediate rejection. No further work is required for this analysis request.
