---
entry: 0026
title: Plot completed Bgx minibinder and nanobody overviews
date: 2026-09-17
author: GPT-6
type: audit
status: complete
machine: Apple M4 Max, 64 GB (historical campaign attribution); no new inference measurements
tags: [analysis, figures, minibinders, nanobodies, timing]
---

## Context

After project Lab Book entry 0136, the user requested the same
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
See project Lab Book entry 0138 for the matching implementation record.

Figures and numerical timing table: [generated report](../output/bgx_completed_overviews_v1/REPORT.md).

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

## Follow-up — actual minibinder lengths (2026-09-17)

Added mean binder length beside each minibinder timing bar and to a new
`minibinder_campaign_lengths.csv` plus the report timing table. Verified cached
lengths against all 3,500 original optimized sequence records and their preserved
summary-file hashes. Length is constant across each trajectory's five cycles;
n=50 trajectories per campaign. Across all seven engines, h0 averages 111.06 aa
and h1 averages 96.18 aa (displayed to one decimal). Timing remains seconds per
optimized design, not seconds per residue. All 14 SVG labels and export hashes
passed checks; the updated PNG was visually inspected. Reproduced with
`analyse.py --plot-only` and `write_report.py`; no inference or new timing study.

## Follow-up — initialization pairing and timing limits (2026-09-17)

Read all 700 minibinder initialization plans and verified each against its
cycle-00 summary sequence. All seven engines share per-run lengths, sampling
seeds and recorded mask positions within h0 and within h1. Six engines also
share identical literal masked sequences; OpenFold instead has amino-acid
substitutions and no literal X tokens, with some additional unmasked-position
differences in h1. Consequently identical mean lengths do not imply identical
inputs across all seven engines. Details are recorded in project Lab Book 0138.

The historical longer-condition timing costs are lower by 3.14% for Boltz,
0.76% for IntelliFold Flash and 2.51% for Protenix v2, calculated from the
existing `timing.csv` on the attributed Apple M4 Max hardware. All four other
engines have higher costs for the longer condition. The conditions differ in
seed, sequences and helix control as well as length; the elapsed-time metric
also includes initialization, MPNN and internal gaps. No controlled length
benchmark, repeatability test or causal attribution was performed. No raw
outputs, plots or settings were changed.
