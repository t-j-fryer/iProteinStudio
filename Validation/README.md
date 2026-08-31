# iProteinStudio Validation

This tree separates reproducible settings experiments from application code and
from user projects. Experiment code, manifests, compact result tables, SVGs and
captions are tracked. Large predictor outputs and caches are ignored.

The first campaign, `resident_design_v1`, is one controlled three-arm question:
how much end-to-end time is saved by cycle waves and true cross-cycle residency
relative to the current per-trajectory implementation? It runs six design
engines with 12 trajectories, five design cycles, fixed 80-aa binders, one
predictor seed/sample and an exact cached SUMO MSA. Helix suppression and
experimental IntelliFold padding are excluded so they cannot confound speed.

The resident worker is implemented but validation-gated. It is not exposed as
an app default until the full output audit and lifecycle gates in
`docs/RESIDENT_INFERENCE.md` pass.

Start with `python3 Validation/experiments/resident_design_v1/campaign.py plan`.
The generated manifest records all commands before GPU time is spent.
