---
entry: 0138
title: Plot completed Bgx minibinder and nanobody overviews
date: 2026-09-17
author: GPT-6
type: audit
status: complete
machine: Apple M4 Max, 64 GB (historical campaign attribution); no new inference measurements
tags: [analysis, figures, minibinders, nanobodies, timing]
---

## Context

After [[0136-restart-outstanding-openfold-runs]], the user requested the same
plot as the v7 binding study's `01_overview.svg` for these completed minibinders,
and a nanobody version replacing helix conditions with scaffolds, omitting
secondary structure and pooling time per design across scaffolds per engine.

## What was done

Created `Validation/experiments/bgx_completed_overviews_v1/` with a declared
70-campaign manifest, reusable analysis, report writer, README and focused
statistical/timing tests. Reused the reference study's chain/sequence/finite
coordinate reader, Biotite P-SEA and overlap-aware timing-span helper. Read the
original campaign snapshots and outputs without modifying them.

Exported two matching Arial/transparent SVG overviews, PDF and PNG versions, a
combined PDF, gallery, report, cycle and trajectory data, timing tables, source
hashes, per-campaign settings/MSA/snapshot provenance and output checksums under
`Validation/output/bgx_completed_overviews_v1/`. Nanobodies use 56 scaffold rows
and seven timing bars. Inspected both rendered PNGs and corrected crowded labels.
See Validation entry [[0026-bgx-completed-overviews]].

Figures and numerical timing table: [generated report](../Validation/output/bgx_completed_overviews_v1/REPORT.md).

## Results

Historical-output analysis; no new benchmark measurements or model inference.

- Audited 5,250 optimized structures from 70 campaigns: 3,500 minibinder and
  1,750 nanobody structures, representing 1,050 five-cycle trajectories.
- All summary cardinalities, chain sequences, finite coordinates, normalized
  versus native structure bytes and summary versus normalized iPTM checks passed.
- Binder confidence uses chain-A Cα pLDDT, not complex-average confidence.
  Minibinder P-SEA fractions are computed from coordinates; cycle 00 is excluded.
- Dots are trajectory means; diamonds are condition means; bootstrap CIs use
  10,000 trajectory resamples. n=50 per minibinder arm and n=6/7 per scaffold.
- Verified 15,586 extraction-source hashes, secondary-structure fraction sums,
  both SVG panel sets and all exported checksums. Four mathematical/accounting
  tests passed, including unequal scaffold budgets and overlapping timers.
- Timing is recorded campaign span divided by optimized outputs. Nanobody spans
  are summed over eight scaffolds and divided by 250 outputs per engine, excluding
  gaps between campaigns. Exact measured historical values are in the report and
  `timing.csv`; no new timing or causal performance claim is made.

## Decision and rationale

Match the requested figure's trajectory-level statistical unit rather than
pooling 250 correlated cycles as independent observations. Pool nanobody time
with output weighting because two scaffolds received seven trajectories and the
others six. Retain initialization cost in timing, as in the reference; do not
sum overlapping resident trajectory durations. Draw one timing aggregate per
engine without spurious error bars.

## Reproduce

```bash
MPLCONFIGDIR=/tmp/bgx-overviews-mpl \
  "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" \
  Validation/experiments/bgx_completed_overviews_v1/analyse.py
python3 Validation/experiments/bgx_completed_overviews_v1/write_report.py
MPLCONFIGDIR=/tmp/bgx-overviews-mpl \
  "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" \
  -m unittest discover -s Validation/experiments/bgx_completed_overviews_v1 -p 'test_*.py' -v
```

Analysis HEAD: `04fcab788f46e0c53c96927757bb6e6388ba210d` (dirty worktree).
Biotite 1.6.0; NumPy 2.4.1; Matplotlib 3.11.1. Source and artifact SHA-256 values
are recorded with the exports. The extraction source before visual-only layout
adjustments is preserved separately from the final rendering-source hash.

## Limits and what was not tested

Minibinder h0/h1 differ in length ranges (65–150 versus 65–120 aa) and seeds;
no paired causal helix comparison is claimed. Native engine settings and model
confidence calibration differ. Nanobody scaffolds range 115–128 residues; full
binder confidence includes the framework. Timing includes pauses inside a
recorded span, excludes pre-timer setup/queueing, and is not pure GPU latency.
No orthogonal prediction, binding experiment, new model inference, repeated speed
experiment, historical model-byte equivalence proof or full geometry-violation
reclassification. No Swift build was needed: no application code changed and
no commit was made. Existing unrelated work was preserved.

## Next

Use the exported SVG/PDF figures; any final-hit comparison needs its own explicit
analysis and independent validation. No settings were promoted.

## Follow-up — mean length beside timing bars (2026-09-17)

At the user's request, annotated each of the 14 minibinder timing bars with
seconds/design and actual mean binder length, in amino acids. Verified all
3,500 cached minibinder cycle lengths against the original summary sequences
and their recorded source hashes, and confirmed length remains constant across
all five cycles of each trajectory. Each campaign has 50 trajectories: mean
length is 111.06 aa for h0 and 96.18 aa for h1, identical across the seven engines
within each condition. The plot displays 111.1 and 96.2 aa; it does not normalize
time per residue.

Regenerated SVG, PNG, PDF, combined PDF, gallery, report and checksums using
`analyse.py --plot-only` then `write_report.py`. Added exact lengths to
`summary.json`, `minibinder_campaign_lengths.csv` and the report's timing table.
Visually checked the rendered plot and verified all 14 SVG length labels and all
export hashes. No new inference or coordinate reassessment was performed for
this annotation-only revision.

## Follow-up — shared initialization and timing interpretation (2026-09-17)

Compared all 700 minibinder `run_*/secondary_structure_plan.json` records
(50 starts × two conditions × seven engines), and verified every saved
cycle-00 `binder_sequence` in `summary_all_runs.csv` matches its plan. Within
each condition, all engines have identical lengths, sampling seeds and recorded
mask positions for each corresponding run. Boltz, both IntelliFold variants
and all three Protenix variants also have identical starting sequence strings
for all 50 runs. OpenFold's saved starts contain no literal X tokens: its
initialization substitutes amino acids at the recorded masked positions.
Thus all seven share length sampling, but only six share literal masked inputs.
OpenFold also differs at some unmasked positions in h1; do not describe its
inputs as otherwise identical. The two conditions use different seeds and
requested length ranges. Identical within-condition length means are expected
from this shared sampling, rather than a plotting error.

Rechecked historical `timing.csv`: longer h0 versus shorter h1 costs are
25.3982 versus 26.2206 seconds/output for Boltz, 44.8320 versus 45.1754 for
IntelliFold Flash, and 92.9024 versus 95.2973 for Protenix v2. These are 3.14%,
0.76% and 2.51% lower respectively on the historical Apple M4 Max campaigns;
the other four engines have higher costs in h0. These descriptive differences
do not establish a length effect. The metric includes initialization, MPNN and
gaps inside each campaign span and is divided by 250 optimized cycle outputs;
conditions also differ in helix control, seed and sequence inputs. No repeated
timing experiment or causal explanation of the small reversals was tested.
Raw data and figures were not changed; no inference, application change or
Swift build was performed.
