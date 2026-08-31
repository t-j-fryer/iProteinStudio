---
entry: 0001
title: Compare current, cycle-wave and resident iterative prediction
date: 2026-08-30
author: codex
type: experiment
status: in-progress
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
completed both prediction waves. The 18 full campaigns remain to be launched.

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
this experiment. No optimized scheduler is promoted until the full matrix and
output audit complete.
