---
entry: 0006
title: Compare transient and sustained secondary-structure sequence priors
date: 2026-09-04
author: gpt-5.6
type: experiment
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, secondary-structure, beta-sheet, anti-helix, boltz]
---

## Context

Entry 0085 in the project Lab Book introduced explicit anti-helix and β-oriented
sequence priors. The first implementation applied the prior both to cycle 00 and
every later MPNN redesign. The scientific question is now split: does changing
only the initial sequence affect the trajectory, or must the prior remain active
during redesign?

## What was done

Declared five matched aCbx arms: natural, anti-helix seed-only, anti-helix
seed-and-cycles, β seed-only, and β seed-and-cycles. Each full arm requests 10
90-aa trajectories and five optimized cycles. Anti-helix strength is 0.50; all
three β strengths are 0.50. Boltz is resident, SolubleMPNN redesigns the whole
binder, target MSA is checksum-pinned, and loop kill/mixed mode/post-prediction
are disabled.

A one-trajectory-per-arm end-to-end smoke gate precedes the full jobs. MCP v8
creates immutable plans and queues jobs behind the shared Apple-GPU execution
lock. The gate requires all six cycle structures and confirms byte-identical
cycle-00 sequences within each seed-only/sustained pair.

## Results

The end-to-end smoke gate passed on 2026-09-04. Every arm produced the expected
six coordinate files (cycle 00 plus cycles 01–05), for 30/30 structures total.
The anti-helix seed-only and seed-and-cycles arms had byte-identical cycle-00
sequences. The corresponding beta arms were also byte-identical at cycle 00.
The natural arm used a distinct seed sequence, as intended. The established 50%
Boltz `X` mask was retained in cycle 00; the first SolubleMPNN redesign replaced
the mask with standard amino acids.

After the gate passed, all five full 10-trajectory plans were queued through MCP
v8. Job identifiers are:

- natural: `job-bf3d47bcb2a1`
- anti-helix seed-only: `job-fa3b9d81b17b`
- anti-helix seed-and-cycles: `job-168f9e407d1d`
- beta seed-only: `job-9b880cec721c`
- beta seed-and-cycles: `job-4ec41862d359`

The sustained anti-helix job acquired the shared Apple-GPU lock first; the other
four remained queued rather than oversubscribing unified memory. Full scientific
results are not yet available and no effect size is claimed.

## Decision and rationale

The primary comparison is a paired five-arm experiment. Mixed mode is excluded
because it would confound whether β-oriented composition or anti-helix pressure
caused a change. Independent confirmation folds are excluded at the user's
request; the design-engine coordinate outputs are sufficient for this first
mechanistic test, not for claiming validated binders.

## Reproduce

See `Validation/experiments/secondary_structure_priors_v1/README.md`.

## Limits and what was not tested

- Full jobs are running/queued; their output cardinality and P-SEA analysis have
  not yet been completed.
- Only one target, fixed 90-aa binders and 0.50 strengths are tested.
- No mixed prior, loop kill, independent predictor or M1 validation is included.
- P-SEA assignment measures predicted secondary structure, not experimental
  folding or solubility.

## Next

Wait for the full arms, audit exact output cardinality, run per-structure P-SEA,
and compare paired changes across cycles 01–05.
