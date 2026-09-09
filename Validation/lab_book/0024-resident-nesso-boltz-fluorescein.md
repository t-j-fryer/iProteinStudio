# 0024 — Resident NESSO versus Boltz2 on fluorescein designs

Date: 2026-09-09. Status: complete; audited. Hardware: Apple M4 Max,64 GB, macOS 26.6.1.


## Context

The user requested a matched 50-design ligand scoring speed and metric-agreement
comparison using resident models, with competing Studio design runs temporarily
stopped. No prior matched comparison was found in Studio or iProteinHunter-beta.
Beta Lab 0044 and its NESSO report measure CPU/MPS portability; Studio Lab 0095
measures Boltz lifecycle. Neither establishes matched NESSO/Boltz ranking agreement.

## What was done

Experiment: `Validation/experiments/nesso_boltz_fluorescein_v1/`.
Raw output: `Validation/output/nesso_boltz_fluorescein_v1/`.
[Final report](../output/nesso_boltz_fluorescein_v1/analysis/REPORT.md)
and [overview](../output/nesso_boltz_fluorescein_v1/analysis/overview.svg).

Selected 50 distinct canonical sequences at evenly spaced historical combined-score
ranks, including endpoints 0.6552–1.9683, from 3,256 eligible unique sequences in
`/Users/thomasfryer/NanoHunter/output/nise_fluorescein/trajectory.csv`. There are
16 source lineages and lengths 65–141 aa. Selection includes designed Phase 0
refinement and NISE descendants, excludes masked initialization, missing/nonfinite
scores and duplicates (first occurrence retained). Copied/hashed historical
structures, input YAMLs, confidence/affinity outputs and the source table;
audited sequences and coordinates before selection was frozen.

Both models receive the same sequence and Boltz-affinity-standardized ligand
chemical state (fluorescein hydroxyethylamide; original charged SMILES and the
neutralized form are recorded). Neither receives a backbone template. Empty Boltz
MSA, no pocket restraints, physical potentials enabled. Native production settings:
Boltz structure 3 recycles/200 steps/1 sample; affinity 5 recycles/200 steps/3 samples.
NESSO refined float32 MPS 5 recycles, fresh ESM-2 embeddings. These are different
architectures/workloads, not a matched-FLOP or equal-diffusion contrast; settings
are fixed within each model and the sequence/seed 17/ligand are paired.

Used the established NISE acceptance experiment's immutable preflight/broker
pattern with exclusive Apple-GPU lease. Complete scripts, model/chemical assets,
source inputs and dependency versions are fingerprinted; no weights redistributed.
Global runtime files and original campaign settings were not modified.

Three low/middle/high cases passed the separate pilot before the 50-case plan.
Every fresh resident session gets one excluded warmup. Exactly one resident worker
per engine served all 50 measured cases, serially NESSO then Boltz. Model-load counts
were 2 (NESSO+ESM, or Boltz structure+affinity), never one reload per sequence.
Timing includes preprocessing, fresh ESM, inference, affinity and normal output
handling; experiment hashing/startup/warmup are separate. Journal receipts audit
all raw artifacts and support unit-level replay into new attempt directories.

Saved/stopped `job-4d54e18d450b` using Studio's broker at 18:05UTC. Completed
checkpoints stayed intact. After benchmark completion, resumed the same batch and
confirmed `running`, engine 6/7 IntelliFold v2 Full, no error; OpenFold3 remains next.
The interrupted cycle may repeat work not covered by a completed checkpoint;
its replay cost is not measured here. Pause/resume receipts are saved with the
benchmark. No manual process suspension or global runtime replacement was used.

## Results

All 50 pairs passed; all 50 NESSO placements were valid. Full benchmark job
`job-79f5b8815b03`, plan `plan-79f5b8815b031a39`. Pilot job`job-c780eb3e71a9`.

| Method | n sequences | Mean s/design | Median s/design | Total seconds |
|---|---:|---:|---:|---:|
| Boltz2 structure + affinity | 50 | 64.357 | 64.101 | 3217.833 |
| NESSO + fresh ESM | 50 | 10.452 | 10.420 | 522.600 |
| NESSO model only | 50 | 2.573 | 2.599 | 128.626 |
| ESM only | 50 | 0.052 | 0.038 | 2.607 |

Boltz/NESSO mean-time ratio **6.157**; paired-case
bootstrap 95% interval 6.066–6.248. This interval excludes
between-run, thermal and machine uncertainty. The residual NESSO request time is
primarily preprocessing/other overhead, not ESM; no optimization speedup is claimed.

| Comparison | n | Pearson r | Spearman rho |
|---|---:|---:|---:|
| nesso_pbind vs boltz_pbind | 50 | -0.116 | -0.215 |
| nesso_placement_confidence vs boltz_ligand_plddt | 50 | 0.274 | 0.206 |
| nesso_combined vs boltz_combined | 50 | 0.223 | 0.106 |
| historical_score vs boltz_combined | 50 | 0.989 | 0.992 |

Combined-score top-ten overlap is 3/10. A NESSO top 20 shortlist retains only 4/10
of the Boltz top ten; top 30 retains 6/10. NESSO ranking uses
P(bind)+(1−entropy_crop_pl), rejecting missing/nonfinite/out-of-range or <= 1e-6
entropy. Boltz ranking uses P(bind)+ligand pLDDT/100. Full entropy and raw affinity
outputs are also reported. No rank is imputed for invalid placement.

The three pilot/full repeats have exactly matching NESSO P(bind) and cropped
entropy. Boltz repeat maximum absolute changes are 0.005790 in P(bind) and 0.278387
ligand-pLDDT points. This is a bounded repeat check, not a general determinism study.

Five experiment tests passed, including synthetic full-report generation,
selection exclusions, invalid-entropy handling, known timing/rank mathematics and
tampered-receipt rejection. Final analysis rehashed 100 full receipts and all their
recorded artifacts. Overview PNG/SVG visually inspected. `git diff --check` passed.
The final report generator is archived as `analysis/generator.py` and hashed in
`analysis/artifact_audit.json`; the initial generator is also retained in the
immutable full-plan snapshot. Only derived analysis was regenerated.

## Decision and rationale

NESSO is substantially faster for this scoring path, but poorly reproduces the
Boltz ranking. Fresh Boltz agrees closely with historical Boltz, so unstable
Boltz reruns do not explain the disagreement. This cohort does not validate
NESSO placement entropy as ligand pLDDT, nor a narrow NESSO-only shortlist intended
to retain Boltz-favored candidates. Keep it experimental; do not promote a scoring
default or modify the app automatically. Experimental binding data would be
needed to judge which model is more accurate, rather than merely more concordant.

## Reproduce

See the experiment README for preparation, pilot/full preflight and broker start.
Exact full digest:
`79f5b8815b031a39a0ce171dc8cb291a8f3720268b150438e0ee988a9411a62b`.

```bash
python3 Validation/experiments/nesso_boltz_fluorescein_v1/analyse.py --output Validation/output/nesso_boltz_fluorescein_v1
python3 -m unittest discover -s Validation/experiments/nesso_boltz_fluorescein_v1 -p 'test_*.py'
```

## Limits and what was not tested

One ligand, one M4 Max/64 GB machine, related sequences, selected historical score
range, one measured pass per model and fixed engine/candidate order. Pilot had
three cases per model (mean Boltz 79.857 s, NESSO 10.395 s); pilot is separate from the
full timing estimate. Startup/warmup are recorded separately. CPU/MPS parity was
not repeated; only native MPS is measured here. The documented Boltz linalg SVD
CPU-fallback warning occurred once in each Boltz worker log; this is a warning
count, not an operator-call count. No generic MPS fallback was enabled.

No experimental affinity truth, alternative ligand, whole NISE search, optional
UI-shortlist integration, prolonged memory soak, fault-injection campaign, new
app/DMG or Swift change. Swift build was not run and no commit was made. Setup
initially encountered sandbox-denied hardware `sysctl`; authorized hardware access
resolved it without changing selection. No scientific inference failed.

## Next

Validate NESSO against experimental labels or broader independent ligand cohorts
before using it for aggressive exclusion. Separately investigate the measured
preprocessing overhead if improving throughput; do not conflate that engineering
opportunity with evidence that the ranking objective works.

Project entry: [0118](../../lab_book/0118-resident-nesso-boltz-fluorescein.md).
