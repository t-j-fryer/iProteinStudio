# Full analysis of the v7 binding helix-control benchmark

This analysis reproduces the complete output contract used by
`helix_strength_all_engines_v3/analysis/full_analysis_v1`, adapted to the
two-strength, target-conditioned ACBX binder campaign.

Run from the repository root:

```sh
python3 Validation/experiments/binder_helix_strength_full_analysis_v1/analyse.py
python3 -m unittest discover -s Validation/experiments/binder_helix_strength_full_analysis_v1 -p 'test_*.py'
```

The analysis fails if the manifest, stage receipt, frozen experiment code,
staged pipeline code, audit identity, audited raw files, coordinate replay,
target identity, P-SEA assignment, predictor scores, or geometry replay differs.
It does not modify the raw campaign outputs.

The overview includes recorded seconds per optimized design: combined pilot and
remaining design-stage spans divided by 50 cycle01–05 outputs. Initialization is
amortized; overlapping resident timers count once. See `timing.json` for exact
provenance and limitations. Accounting is shared with the monomer full analysis.
