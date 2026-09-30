---
entry: 0233
title: Compare reduced Mac predictions with workstation filtering outcomes
date: 2026-09-30
author: Codex
type: experiment
status: complete; interim two-engine analysis
machine: Apple M4 Max, 40-core GPU, 64GB, macOS26.6.1; CPU analysis only this task
tags: [filtering, validation, paper, performance]
---

## Context
User requests correlation and experimental filtering comparisons against the workstation In_Silico_Filtering package, plus ETA for ongoing674×8-engine Mac campaign. No new inference requested. Preserve running job and original workstation data.

## What was done
Read Validation instructions, workstation analysis methods/cohort audits/threshold reports, score exports, Mac audited prediction export and live receipts. Applied spreadsheets skill to tabular analysis; no workbook authored. Declared `Validation/experiments/mac_workstation_filtering_v1/manifest.json` before calculating results; implemented analyse.py and report.py. All derived artifacts under `Validation/output/mac_workstation_filtering_v1/snapshot_20260930/`. Source CSVs snapshotted and hashed. No model imports or predictions; NumPy/Pandas/SciPy/sklearn/Matplotlib CPU analysis.

Boltz/Flash each674 predictions complete; primary paired cohort563/85 validated hits. OpenFold complete but openDDE is a different model, not paired. Mini running; v2/Constraint/ESM pending at analysis. Hash-verified completed receipts used for count/ETA. Standard job-status call attempted a routine state refresh outside writable roots and failed permissions; read state.json and live logs/receipts instead without changing jobs.

## Results
Historical F2 metric held fixed: Boltz workstationAP0.366610→Mac0.374894, top50hits18→24, top10042→40; Flash0.394200→0.384399, top5020→21, top10044→45. Median-workstation versus single-Mac ipSAE Spearman0.912534/0.919604; ipTM0.919837/0.926843; interfacePAE0.928292/0.946891. Paired2000-bootstrap AP-difference95% intervals Boltz[−0.039590,+0.051160],Flash[−0.054260,+0.041672]. No noninferiority margin or equivalence claim.

SUMO AP declines0.463→0.437 and0.413→0.371; small ProteinA/TrxA gains offset pooled results. Fixed workstation Boltz cutoff0.790636 retrieves48/108 then29/66 on Mac: rank utility does not imply cutoff transfer. Primary endpoint, strict550-design cohort, assayed-sequence mismatch exclusion and same-median-metric sensitivities recorded.32 screened assayed-sequence mismatches are all validated hits; excluding them is outcome-associated, not a new primary cohort.

## Decision and rationale
Encouraging retrospective ranking/shortlist preservation for two engines, with target dependence and changed individual shortlists. Cannot isolate effects of128-row MSA/25 steps: Boltz potentials differ, sample summaries differ, source/runtime/ipSAE provenance is incomplete, and workstation binder sequences are unavailable. Preserve native score meanings; do not invent OpenFold PAE or treat openDDE as the same engine.

ETA uses live mean request times where available and five actual SUMO qualification-complex means for queued engines, with10% central overhead and explicitly judgement-based0.7–1.6× planning envelope. Approximately22h remaining around analysis time; latest timestamp/counts and finish in progress_eta.json. Long-target variation, retries, thermal/runtime drift and audit can change this. OpenFold−9 attempt recovered automatically; no cause asserted.

## Validation and reproduce
Independently recomputed all three experimental label sets from reanalysis assay inputs; exact matches. Historical F2 AP reproduced to1e-12 for both engines. Exact unique joins, target hashes/lengths and binder lengths checked; measurement hashes checked. Four actual ranking/AP/tie/zero-hit toy checks pass. Figure PNG visually reviewed; no clipped labels. Script/source hashes, dependencies and raw input hashes recorded.

`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/iprotein-filtering-mpl Validation/output/esmfold2_mlx_update_v1/venv/bin/python Validation/experiments/mac_workstation_filtering_v1/analyse.py --workstation /Users/thomasfryer/Coding/AI_DBTL_PAPER/Screening/Nanopore_Consensus_Reanalysis/Integrated_Analysis/In_Silico_Filtering --output NEW_SNAPSHOT_DIRECTORY`

Then `report.py NEW_SNAPSHOT_DIRECTORY` in the same environment. Independent truth verification receipts in validation.json; no source writes.

## Limits and what was not tested
Only completed paired Boltz/Flash; no raw workstation single-seed reference, calibrated causal settings comparison, family-aware uncertainty, prospective experimental success or other-Mac generalization. Bootstrap design-level within target ignores family dependence. Unvalidated benchmark non-hits are not proven nonbinders. Mac single sample versus workstation p90/min or median summaries is explicit. No additional GPU work, app edits, releases, commit or Swift build. Broad campaign remains active.

## Next
As v2/ESM complete, extend paired maps and confirm original source/metric definitions before adding them. Do not interpret after-only Mini/OpenFold/Constraint as matched workstation comparisons.
