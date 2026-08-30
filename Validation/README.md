# iProteinStudio Validation

This tree separates reproducible settings experiments from application code and
from user projects. Experiment code, manifests, compact result tables, SVGs and
captions are tracked. Large predictor outputs and caches are ignored.

The first campaign, `resident_design_v1`, tests three independent questions:

1. whether the existing per-trajectory scheduler and cycle-wave directory
   scheduler produce complete, resumable 12-trajectory × 5-design-cycle runs;
2. whether a genuinely campaign-resident model process is faster without
   changing requested work or outputs, after its currently disabled worker arm
   passes lifecycle gates; and
3. whether maximum helix suppression shifts designed-binder secondary structure.

These are not collapsed into one two-arm comparison. Helix suppression changes
sequences and can therefore change inference time and quality; it is not a valid
speed control. IntelliFold's length-aware padding is likewise a separate paired
contrast; Boltz and Protenix do not receive artificial length buckets.

“Helix suppression” here names Studio's cycle-00 sequence-initialization bias.
It does not claim that every predictor or SolubleMPNN receives a persistent
secondary-structure potential. Cycle 01–05 P-SEA measurements test whether the
initialization effect survives the actual design loop.

Start with `python3 Validation/experiments/resident_design_v1/campaign.py plan`.
The generated manifest records all commands before GPU time is spent.
