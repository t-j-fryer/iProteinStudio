# Completed Bgx overview figures

Retrospective analysis of the 70 completed desktop campaigns listed in
`manifest.json`. No model inference or default promotion. Raw jobs stay under
`NANOHUNTER_ROOT/projects/untitled_design` (default `~/.iproteinstudio`). Outputs:
`Validation/output/bgx_completed_overviews_v1/`.

Reuses the reference v7 figure's validated chain/sequence/coordinate reader and
Biotite P-SEA assignment, and its timing-span helper. Binder Cα pLDDT is read
from the predicted structure; complex-average confidence is not substituted.
Normalized confidence iPTM must agree with the summary. Cycle 00 is excluded
from scientific endpoints and included in amortized timing cost.

All five cycles are averaged within each trajectory first. Dots are trajectory
means; diamonds are condition means; intervals are deterministic 10,000-resample
95% bootstrap intervals over trajectories (n=50 for minibinders; n=6 or 7 per
nanobody scaffold). The two minibinder conditions differ in lengths and seeds;
no paired effects or causal helix-control claim is made.

Campaign time is latest recorded trajectory end minus earliest start, so
resident overlap counts once. Nanobody engine time sums the eight separate
campaign spans and divides by 250 completed optimized outputs. This weights
scaffolds by their six/seven trajectories and excludes inter-campaign queue
waits. No interval is drawn for aggregate timing. These are descriptive costs
of historical native-setting campaigns, not controlled speed comparisons.

```bash
MPLCONFIGDIR=/tmp/bgx-overviews-mpl \
  "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" \
  Validation/experiments/bgx_completed_overviews_v1/analyse.py
MPLCONFIGDIR=/tmp/bgx-overviews-mpl \
  "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" \
  -m unittest discover -s Validation/experiments/bgx_completed_overviews_v1 -p 'test_*.py' -v
```

SVG exports use transparent backgrounds, editable Arial text, inward ticks,
black axes/outlines and no grid. PDF and PNG previews are also exported, along
with a two-page PDF, gallery, source hashes, per-cycle/per-trajectory values,
per-campaign timing and per-engine pooled nanobody timing. `--plot-only` redraws
from the derived cache; use a full run to re-audit raw inputs.

Refresh the report and export hash manifest after rendering:

```bash
python3 Validation/experiments/bgx_completed_overviews_v1/write_report.py
```

Minibinder timing labels also show actual mean binder length (aa) across the
50 trajectories in each campaign. Exact means are saved in
`minibinder_campaign_lengths.csv` and the report. Lengths were verified against
the original optimized sequences and remain constant within each trajectory.
Timing is presented per optimized design, without per-residue normalization.
