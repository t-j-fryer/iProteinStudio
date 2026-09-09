---
entry: 0093
title: Localize coil and finish retrospective screening tools
date: 2026-09-05
author: gpt-6
type: analysis-and-implementation
status: analysis complete; adaptive optimization not implemented
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1
tags: [secondary-structure, confidence, analysis, validation]
---

## Context

The user requested localization of extra coil, testing of seed interventions,
and consideration of local cycle-00 remasking with a loose progression gate and
natural-protein composition bins. Subsequent messages asked to finish the code
and report its status. This follows project0092 and Validation0010.

## What was done

Completed diagnose.py and its tests under
Validation/experiments/secondary_structure_coil_v1/. The analysis reverified all
120 coordinate hashes and20 seed plans from the preceding two-arm experiment,
recomputed PSEA, and retained exact requested sequences and per-residue confidence.
Produced residue, segment, structure and trajectory tables plus reviewed heatmaps
under Validation/output/secondary_structure_coil_v1/diagnosis/.

Implemented analysis adapters for declared intervention outputs, paired summaries
and a status/audit monitor. Their existing-data audit successfully checked all120
prior structures; the summary reader reverified394 hashes and recomputed60
reference structures. A new experiment driver/config was drafted but never run.
No new scientific runtime, weights or completed raw outputs were changed.

Added reference_bins.py with tests. It accepts an explicitly curated table,
keeps fold/support strata separate, checks PSEA version and cluster uniqueness,
reports incomplete assignments and produces descriptive joint H/S/C bins. It
never invents reference observations or acceptance thresholds. research.md records
primary sources and an appropriate reference-cohort plan. No cohort downloaded.

The adaptive sequence-generation subtask was stopped by a biological-safety
check. Adaptive remasking and automatic progression into cycling remain
unimplemented for the current toxin-targeted campaign. No new optimization jobs
were launched. README.md explicitly distinguishes executed tools from draft and
untested components; no claim is made that all requested approaches are finished.

## Results

Across optimized cycles01–05, mixed-minus-beta extra coil is12.24 percentage
points of all binder residues. Internal coil contributes11.40points; segments of
at least16 residues contribute9.73points. Low-confidence coil below50 contributes
7.76points and intermediate-confidence coil50–70 contributes6.82points; confident
coil decreases2.33points. These are descriptive trajectory-balanced differences.

Much of the low confidence recovers: at cycle05, residues simultaneously coil
and pLDDT<50 occupy0% of beta binders and2% of mixed binders. A retrospective
16-residue coil/visible-mean-pLDDT<50 flag selects5/10 mixed starts; these naturally
reach mean final binder pLDDT80.06, and one reaches the optimized structural target.
A broad low-confidence-coil cutoff would flag all three passing mixed trajectories.
These retrospective thresholds are not validated disorder classifications.

All20 tests passed:8 diagnosis,6 analysis/monitor and6 reference-binning tests.
The reference tests use synthetic count fixtures only. git diff --check passed.
No new biological intervention outcome or measured natural distribution exists.

## Decision and rationale

Keep coil geometry and confidence separate. Long internal coil is a legitimate
analysis focus, but substantial confidence recovery makes permanent rejection of
poor-looking cycle00 starts unsupported by these data. Preserve originals and
report false rejection in any future authorized, appropriate benchmark.
Natural reference bins are descriptive strata, not universal acceptance rules.

## Reproduce

```bash
MPLCONFIGDIR=/private/tmp/iproteinstudio-mpl ~/.iproteinstudio/venvs/NanoHunter_protenix/bin/python Validation/experiments/secondary_structure_coil_v1/diagnose.py
MPLCONFIGDIR=/private/tmp/iproteinstudio-mpl ~/.iproteinstudio/venvs/NanoHunter_protenix/bin/python -m unittest discover -s Validation/experiments/secondary_structure_coil_v1 -p 'test_*.py'
```

Scientific fingerprints remain in the prior experiment's manifest_full.json and
stage_receipt.json (commit37cc95497283025191e7d2067cb35d1af9168d72 plus recorded dirty
hashes, exact target MSA and checkpoint fingerprints). No additional inference.

## Limits and what was not tested

No new seed intervention folds, local-remasking folds, adaptive progression,
new three-arm monitor completion, natural-reference cohort, orthogonal predictions
or experimental biology. No app build or commit. Existing-data checks and unit
tests do not substitute for end-to-end validation of the draft experimental code.

## Next

The analysis-only tools are ready. Further adaptive optimization is not completed
for the current campaign. Keep this status explicit when handing off the code.
