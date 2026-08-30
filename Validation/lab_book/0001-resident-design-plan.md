---
entry: 0001
title: Validate resident iterative prediction and helix control
date: 2026-08-30
author: codex
type: experiment
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, persistence, batching, token-padding, secondary-structure]
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

- Does live residency remain correct across cycle 00 plus five redesign cycles?
- What incremental speed remains after fair directory-per-cycle batching?
- Does length-aware IntelliFold padding help 65–150-aa minibinder campaigns?
- Does maximum helix suppression alter DSSP-class secondary structure in cycles
  01–05 across engines?

The current helix control is an initialization intervention: it biases the
cycle-00 random binder away from helix-prone residues and changes the UNK patch
policy. It is not a hidden predictor potential and is not reapplied as an MPNN
amino-acid bias at every redesign. The experiment therefore asks whether that
initial condition propagates through iterative inverse folding, not whether a
direct secondary-structure restraint forces every later cycle.

## Design

Target: SUMO, 96 aa, using an exact cached A3M whose sequence and SHA-256 must
match the declared fixture. Each engine receives 12 trajectories, five design
cycles, one predictor seed/sample and the same MPNN/binder seeds.

Speed is paired at helix suppression off:

- `standard_off`: existing per-trajectory scheduler;
- `cycle_wave_off`: one directory process per cycle, the current load-amortized
  control;
- `cycle_wave_length_aware_off`: IntelliFold-only cycle waves using 32-token
  candidate bands ending at the exact campaign maximum;
- `resident_off`: one live predictor model across all available cycles.

Helix control is paired within the resident scheduler:

- `resident_off`;
- `resident_max`: identical settings with helix suppression enabled at 1.0.

The resident arms are declared but disabled until a real request-serving worker
passes lifecycle and resume tests. The executable first phase uses
`standard_off`, `cycle_wave_off`, the IntelliFold-only length-aware arm and
`cycle_wave_max`; it must not be reported as a resident-model result.

For the executable phase, helix suppression pairs `cycle_wave_off` against
`cycle_wave_max` for Boltz and Protenix. IntelliFold pairs
`cycle_wave_length_aware_off` against `cycle_wave_max`, so padding policy is
held constant. Speed comparisons never use a helix-suppressed arm.

Cycle 00 is audited but excluded from design counts and secondary-structure
endpoints. Engines: Boltz 2, IntelliFold v2-flash, IntelliFold v2, Protenix v2,
Protenix Mini and Protenix Constraint v0.5. Constraint runs use the same explicit
SUMO pocket residues recorded in the campaign configuration; other engines only
receive epitope controls they implement.

## Promotion gates

No resident mode becomes the app default unless it is faster in the paired full
campaign and passes: exact job count, exact submitted sequences, finite complete
backbones, confidence presence, MPS proof, reverse-order seed invariance,
interruption/resume, worker-death failure, cancellation and bounded-memory soak.

## Results

The full manifest-frozen matrix is not run. Bounded native-MPS cycle-wave launch
tests completed for all six requested engine choices. One-input directory wall
times were 37.59 s (Boltz 2), 48.93 s (IntelliFold v2-flash), 234.17 s
(IntelliFold v2), 98.49 s (Protenix v2), 17.03 s (Protenix Mini) and 62.58 s
(Protenix Constraint after repair). These are one-shot acceptance timings, not
comparative throughput estimates.

Boltz also completed cycle 00 → SolubleMPNN → cycle 01 and an idempotent resume.
P-SEA assigned every residue in the resulting 131-aa cycle-01 binder. Protenix
Constraint initially failed at 227 tokens because an absent substructure channel
requested a 39.57-GB attention buffer. A checkpoint-equivalent zero-feature
shortcut agreed with the explicit path to maximum absolute error 9.54e-7 on MPS
and reduced the successful job's synchronized driver allocation to 3.98 GB.
After repair, all six engines passed strict availability checks and the complete
configuration expanded deterministically to 20 manifest-frozen campaigns. The
full 20-campaign manifest was planned but not launched.

## Reproduce

```bash
python3 Validation/experiments/resident_design_v1/campaign.py plan
caffeinate -dimsu python3 Validation/experiments/resident_design_v1/campaign.py run
python3 Validation/experiments/resident_design_v1/campaign.py analyze
```

## Limits and what was not tested

The plan covers one protein target and Apple M4 Max. Ligands, nanobody scaffolds,
other Apple chips and post-predictor stages require separate validation. A
query-only binder MSA and cached target MSA are mandatory; online MSA search is
not part of this experiment.
