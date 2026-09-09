# Unconditioned monomer secondary-structure screen

Prospective experiment requested 2026-09-05. Each condition has ten paired
90-residue trajectories, one original initialization prediction and five
SolubleMPNN → Boltz-2 optimization cycles. Inspection uses the existing β prior.
There is no target, ligand, supplied fold, binding metric endpoint or target MSA.

`config.json` declares 22 conditions and each condition's reference. The five
core conditions are baseline, antihelix, beta, mixed and beta_inspection.
Additional single-factor contrasts cover initialization-only versus sustained
priors; antihelix strength; β residue, pattern and turn weighting; 50% versus 0%
X masking; mask-first versus sample-then-mask; loopkill/proline suppression;
first and later MPNN temperatures; first and later global proline logit bias;
and inspection attempt budget, uncertain-coil length and confidence threshold.
This screens all these control families at declared settings; it is not an
exhaustive continuous or interaction sweep. Length, predictor, sample count,
MSA policy and prediction seeds remain fixed.

Each arm's first trajectory is its operational smoke test and remains in the
final ten. The remaining nine start only after that arm passes coordinate,
sequence, cardinality, seed, scope, journal and MPS audits. Inspection exhaustion
is a valid experimental outcome and prevents optimization for that trajectory;
it is never a successful initialization and seeds are never replaced. A
technical failure stops the controller and preserves bridge diagnostics.

At most 1,380 scientific prediction calls are requested: 220 original initializations,
1,100 optimization calls and 60 extra initialization attempts. Studio also
performs its recorded calibration (up to 44 calls across the two phases and
22 arms); calibration is excluded from scientific endpoints. Exhaustion may
reduce optimized output counts. The original initialization is excluded from
design counts and optimization endpoints. Inspection settings are exploratory:
up to three total attempts, a run of at least 16 coil residues each below pLDDT
50; variants independently use one attempt, length eight, or threshold 70.
These are eligibility criteria, not experimental folding/disorder cutoffs.

## Execution and reproducibility

Run from the canonical Studio repository. `stage` holds the shared execution
lock, checks for active jobs, backs up and replaces only the seven explicitly
listed runtime files, verifies MPS, and fingerprints the engine and checkpoints.
`prepare` freezes configuration, experiment code, source identity and runtime
receipt. All execution uses the public immutable `plan-iterative` and `start`
bridge; each plan explicitly records the monomer benchmark's common run
scheduler. The broker's execution lock and script verification remain active.
No model weights are copied into the experiment.

```bash
python3 Validation/experiments/monomer_secondary_structure_v1/test_campaign.py
python3 Validation/experiments/monomer_secondary_structure_v1/campaign.py stage-preview
python3 Validation/experiments/monomer_secondary_structure_v1/campaign.py stage
python3 Validation/experiments/monomer_secondary_structure_v1/campaign.py prepare
python3 Validation/experiments/monomer_secondary_structure_v1/campaign.py run --arm baseline --pilot-only
python3 Validation/experiments/monomer_secondary_structure_v1/campaign.py run
python3 Validation/experiments/monomer_secondary_structure_v1/campaign.py status
```

The long controller should run detached under `caffeinate -dimsu`. Restarting
the controller reuses the existing immutable plans/jobs and verifies completed
audits. It does not silently rerun failed jobs. Generated material lives under
`Validation/output/monomer_secondary_structure_v1/`, including manifest,
requests, plans, status/diagnostics, immutable raw campaigns, per-arm audits and
final `analysis/REPORT.md`, CSV, JSON, SVG and PNG. The runtime project links to
this output; Studio can inspect jobs through its usual result surfaces.

## Analysis

Biotite P-SEA assignments come from predicted coordinates. The primary unit is
the trajectory mean over cycles 01–05; completed trajectories receive equal
weight. Final-cycle fractions, confidence, long uncertain coil, sequence
entropy, acceptance/attempt count and measured complete-trajectory wall time
are secondary outputs. Exhausted trajectories remain in the declared ten,
with conditional metrics labeled by the completed n. Paired bootstrap
intervals resample trajectory differences against the predeclared reference;
they are exploratory and not corrected for multiple comparisons. Raw output
checksums are verified before report regeneration. No default is promoted.
