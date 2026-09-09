---
entry: 0100
title: Inspect the complete monomer secondary-structure benchmark
date: 2026-09-06
author: gpt-6
type: audit
status: complete
machine: Apple M4 Max, 64 GiB unified memory, macOS 26.6.1
tags: [secondary-structure, boltz, validation, statistics, initialization]
---

## Context

The user requested inspection and analysis of the full outputs from
[[0096-monomer-secondary-structure-benchmark]] and its recorded continuation
[[0099-diagnose-and-continue-monomer-screen]]. The continuation finished all
declared conditions and produced its complete report at 05:50:37 UTC.

## What was done

Confirmed all 220 declared trajectories have terminal outcomes and no monomer
campaign job remains active. Read results_overview for the newly completed
cohorts and inspected the final report, its checksum, all 43 original cohort
audits and the supplemental geometry-failure audit.

Added a read-only final inspector under
`Validation/experiments/monomer_secondary_structure_final_v1/review_outputs.py`.
Reverified raw hashes and all frozen pipeline/assessment/geometry identities,
then recomputed coordinate-based P-SEA, finite exact-sequence/CA-confidence
checks and geometry checks for 1,289 cycle-prediction records and 55 journal
prediction records (1,018 unique coordinate/sequence combinations). Reproduced
every initialization assessment under its recorded policy and the single
rejected geometry diagnosis. Reconciled all trajectory aggregates and verified
that every sequence in the loopkill=1 arm is proline-free.

Saved a complete report, paired contrasts, confidence-stratified coil analysis,
inspection attrition decomposition, trajectory CSV, JSON receipts, and SVG/PNG
figures. No new model inference or raw-output edits. A first tooling invocation
failed because the filename `inspect.py` shadowed Python's standard-library
module; renamed it before successful execution. This was an analysis-tool
failure, not a scientific run failure. The final script ran successfully.

## Results

All 22 conditions have ten declared outcomes. Nineteen conditions have ten
completed trajectories. Sample-then-mask has nine, inspection budget=1 has
eight, and inspection coil-length=8 has seven. Totals: 214 completed five-cycle
trajectories, 1,070 optimized structures, five explicit budget exhaustions and
one retained geometry rejection. Cycle 00 never counts as an optimized design.

Primary endpoints average cycles 01–05 within trajectory, then trajectories
equally. Intervals below are paired 95% bootstrap intervals (10,000 resamples),
exploratory and not corrected for multiple comparisons.

- Full proline suppression versus baseline: helix +27.7 pp [14.2, 44.2],
  sheet −10.6 pp [−20.5, −2.1], coil −17.1 pp [−26.0, −8.2], and mean CA
  pLDDT +6.5 [0.2, 12.5]. Resulting means: 71.7% helix, 7.8% sheet, 20.4%
  coil, pLDDT 90.0; final-cycle pLDDT 94.8.
- Sustaining antihelix, β and mixed priors adds 6.3, 3.9 and 3.8 percentage
  points sheet relative to their identical initialization-only starts. Absolute
  sustained-β sheet is only 10.3%. Sustained mixed has 26.8% sheet, 57.5% coil
  and pLDDT 72.6; its pLDDT falls 5.8 relative to initialization-only mixed.
- Removing X masking increases sheet by 14.7 pp [3.7, 25.3] versus β-only,
  alongside coil +12.3 pp [2.4, 20.7]. Sample-then-mask sheet is 17.8% among
  nine completions; its paired sheet gain remains uncertain.
- Later MPNN temperature 0.3 adds only 1.8 pp sheet [0.2, 3.5] versus β-only,
  leaving mean sheet at 8.1%. Lower first temperature and weak P:-0.5 global
  biases do not establish sheet gains. None of the completed controls resolves
  a sheet-enrichment advantage over baseline in the paired intervals.

Inspection outcomes:

| Policy | Completed / declared | Extra initialization predictions | Exhausted IDs |
|---|---:|---:|---|
| Main β inspection | 10/10 | 2 | none |
| One-attempt budget | 8/10 | 0 | 1, 2 |
| Coil length 8 | 7/10 | 11 | 1, 2, 3 |
| Confidence threshold 70 | 10/10 | 2 | none |

The one-attempt policy's eight survivors exactly match the main policy's same
eight IDs. The length-8 policy leaves 0.1% mean sheet and zero final-cycle
sheet. Its apparent +0.37 pLDDT difference decomposes into +1.04 from which
IDs survive and −0.67 within the same seven IDs. A stricter coil screen is
therefore not demonstrated to improve folding or β enrichment. Threshold 70
changes only one trajectory's structural endpoint relative to main inspection.

Coil is not synonymous with uncertainty: initialization-only mixed has 34.7%
of all residues assigned coil at pLDDT ≥70, versus baseline's 25.6%. Sustained
mixed also raises coil below pLDDT 50 to 13.9% of all residues, compared with
7.7% for initialization-only mixed. Confidence bins are descriptive.

## Decision and rationale

Close the declared campaign with all failures retained. Proline suppression
strongly favors helices in this screen; sustained priors influence secondary
structure, but their sheet gains do not establish superiority over baseline.
Keep β enrichment and initialization eligibility as separate evaluation goals.
Do not interpret changes in survivor averages as refinement improvements or
promote an unvalidated default.

## Reproduce

```bash
MPLCONFIGDIR=/private/tmp/iprotein-monomer-final-matplotlib "$NANOHUNTER_ROOT/venvs/NanoHunter_protenix/bin/python" Validation/experiments/monomer_secondary_structure_final_v1/review_outputs.py
```

Set `NANOHUNTER_ROOT` to the managed runtime. This performs analysis only.
Final inspection artifacts:
`Validation/output/monomer_secondary_structure_v1/final_inspection/20260906T161423Z/`.
`final_inspection/latest.json` points to the complete inspection; the underlying
completed campaign report is `recovery_v1/reports/20260906T055037Z/report.json`,
SHA-256 `fc86833cab4bf25cfed8653895aed507f59e6106e7995af6c65506cd68d8bf32`.
The inspection records raw audit and code hashes and archives its source.
Original dirty manifest identity:
`e437e995d3b66874f07ebad29f4d96b228766d6d96b1178b10aabaa21e8cedc2`, base commit
`37cc95497283025191e7d2067cb35d1af9168d72`. Hardware and engine/checkpoint/lock
fingerprints remain in the original stage receipt. Empty MSA; cached-MSA
checksum n/a. The continuation verified full engine hashes before completion.

## Limits and what was not tested

One length, predictor, paired seed cohort and selected settings. No exhaustive
strength/interaction sweep, orthogonal predictor or experimental folding
validation. Bootstrap intervals are exploratory, without multiplicity control.
Conditional structural means explicitly report completed n. SVD warning lines
were preserved (1,305 recorded lines, not a count of individual CPU operations).
No new inference, weight copies, default changes, Swift changes or commit.

## Next

No declared campaign work remains. Any new settings, orthogonal validation or
larger seed cohort should be a separately declared experiment.
