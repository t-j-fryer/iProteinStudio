---
entry: 0001
title: Compare current, cycle-wave and resident iterative prediction
date: 2026-08-30
author: codex
type: experiment
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, persistence, batching, throughput]
---

## Context

ResidentFold exploratory work in iProteinHunter-beta compared fresh processes,
two directory waves and one directory containing all four already-materialized
inputs. Across two paired four-input blocks, the one-directory arm was faster
than two directory processes for Boltz 2, IntelliFold v2-flash, Protenix v2 and
Protenix Constraint. That experiment did not keep a model alive across MPNN
redesign gaps, did not include variable lengths and did not run a complete
iterative campaign. Its copied results remain upstream; no number is promoted
here until reproduced in iProteinStudio.

## Questions

- Does one live model remain correct across cycle 00 plus five redesign cycles?
- What end-to-end speed does true residency add beyond one directory process per
  cycle?
- Does either optimized scheduler preserve all 60 designs and 12 initialization
  structures produced by the current implementation?

## Design

Target: SUMO, 96 aa, using an exact cached A3M whose sequence and SHA-256 must
match the declared fixture. Each campaign receives 12 trajectories, five design
cycles, one predictor seed/sample, one fixed 80-aa binder length and identical
MPNN/binder seeds. Helix suppression is off and IntelliFold uses its established
single 176-token bucket in every scheduler arm.

The three paired arms are `current` (one predictor process per trajectory and
cycle), `cycle_wave` (one directory predictor process per cycle) and `resident`
(one model-owning process across all six prediction waves). Engines are Boltz 2,
IntelliFold v2-flash, IntelliFold full v2, Protenix v2, Protenix Mini and
Protenix Constraint v0.5, for 18 campaigns total. Cycle 00 is audited but not
counted among the 60 designs per campaign.

## Promotion gates

No resident mode becomes the app default unless it is faster in the paired full
campaign and passes: exact job count, exact submitted sequences, finite complete
backbones, confidence presence, MPS proof, reverse-order seed invariance,
interruption/resume, worker-death failure, cancellation and bounded-memory soak.

## Results

All six resident checkpoint choices pass native-MPS launch smokes. Mini, Boltz 2
and IntelliFold v2-flash each completed cycle 00, an intervening SolubleMPNN
redesign and cycle 01 with one worker PID and `model_load_count=1`. Resident
startup/request wall seconds were 8.97/(5.79, 2.18) for Mini,
10.81/(13.62, 13.27) for Boltz and 4.15/(37.66, 34.34) for v2-flash. One-request
checkpoint smokes passed for Protenix v2 (25.71/42.66 s), Constraint
(27.95/34.61 s) and full IntelliFold v2 (5.70/143.39 s).

A rejected double-fork worker lost access to macOS `MTLCompilerService`; workers
therefore remain normal campaign children. The first attached Mini retry exposed
stdout contamination from the Protenix UNK normalizer, which prepended a
diagnostic to the MPNN sequence. Diagnostics now use stderr and inverse-folding
handoffs are explicitly alphabet- and length-validated. The third Mini smoke
completed both prediction waves.

The complete 18-campaign matrix subsequently finished with 1,080/1,080
designed cycle structures (cycle 00 excluded) and no receipt-level audit
errors. End-to-end wall times for current / cycle-wave / resident were: Boltz
2, 40.26/28.35/22.07 min; IntelliFold v2-flash, 47.01/38.52/38.05 min;
IntelliFold full v2, 170.35/153.63/151.04 min; Protenix v2,
84.96/70.44/79.93 min; Protenix Mini, 20.39/4.94/4.54 min; and Protenix
Constraint, 66.43/42.65/40.09 min. Model-load counts were 72, 6 and 1,
respectively.

Protenix v2 was the exception to the otherwise fastest resident arm. Log-level
decomposition shows that this is not model-loading overhead or a memory leak:
mean model-forward time rose from 40.32 s in the one-input current processes to
55.30 s in 12-input cycle waves and 65.14 s in the 72-input resident process,
while resident MPS allocation remained bounded at 2.75--2.82 GB between waves.
Within the first cycle-wave process, forward time rose from 40.38 s for the
first input to 53.93 s for the twelfth. This pattern is consistent with
sustained-load power/thermal throttling or an MPS process-lifetime effect; no
temperature or power telemetry was recorded, so the mechanism remains an
inference. The resident launcher's inherited IntelliFold thread cap was tested
separately on the identical first input: unrestricted and single-threaded
forwards were 36.13 and 37.06 s (64.25 and 66.25 s end-to-end), too small to
explain the full-campaign difference. Protenix v2 therefore retains cycle-wave
scheduling pending randomized-order batch-size and telemetry validation.

## Reproduce

```bash
python3 Validation/experiments/resident_design_v1/campaign.py plan
caffeinate -dimsu python3 Validation/experiments/resident_design_v1/campaign.py run
python3 Validation/experiments/resident_design_v1/campaign.py analyze
```

## Limits and what was not tested

The plan covers one protein target, one 80-aa binder length and Apple M4 Max.
Ligands, nanobody scaffolds, other Apple chips, post-predictor stages, helix
control and mixed-length padding require separate validation. A query-only
binder MSA and cached target MSA are mandatory; online MSA search is not part of
this experiment. Temperature/power telemetry, randomized arm order, Protenix
v2 wave-size optimization, restart/cancellation, reverse-order determinism and
a memory soak remain untested; residency must not be promoted as a universal
default until those gates pass.
