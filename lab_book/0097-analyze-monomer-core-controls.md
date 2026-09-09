---
entry: 0097
title: Analyse the completed monomer core controls during the wider screen
date: 2026-09-05
author: gpt-6
type: audit
status: complete
machine: Apple M4 Max, 64 GiB unified memory, macOS 26.6.1
tags: [secondary-structure, boltz, validation, statistics]
---

## Context

The user requested progress and analysis of [[0096-monomer-secondary-structure-benchmark]].
At the 23:46:25 UTC snapshot all five core conditions have ten complete
trajectories, with five optimization cycles each. The expanded 22-condition
campaign continues. Of 220 declared trajectories, 67 have audited outcomes:
65 completed five cycles (325 optimized structures) and two exhausted budgets
in additional inspection variants. Ongoing trajectories are excluded from this
snapshot. The current job is the remaining sustained-antihelix cohort.

## What was done

Read Studio results_overview for the five completed cohorts, verified all 27
available audit receipts against unchanged raw outputs, and created a separate
read-only interim analysis at `Validation/experiments/monomer_secondary_structure_interim_v1/analyze.py`.
The running experiment's frozen code, settings and raw jobs remain unchanged.
Reconciled the core means independently from P-SEA strings and per-residue
confidence for all 250 optimized core structures across 50 trajectories.
Saved timestamped JSON/CSV, report and transparent SVG/PNG figures.

## Results

Each cell first averages cycles 01–05 within a trajectory, then averages the
ten trajectories. Cycle 00 is excluded. Confidence is mean CA pLDDT (0–100).
These core priors apply to initialization only; sustained controls are pending.

| Condition | n | Helix | Sheet | Coil | pLDDT |
|---|---:|---:|---:|---:|---:|
| Baseline | 10 | 44.0% | 18.4% | 37.5% | 83.5 |
| Helix kill | 10 | 30.2% | 19.1% | 50.7% | 71.1 |
| β prior | 10 | 61.0% | 6.4% | 32.6% | 82.4 |
| Mixed | 10 | 23.7% | 23.0% | 53.4% | 78.4 |
| β + inspection | 10 | 62.0% | 7.4% | 30.6% | 83.8 |

Paired trajectory bootstrap, 10,000 resamples, exploratory 95% intervals:

- Helix kill versus baseline: mean helix −13.8 pp [−31.9, +3.5], coil
  +13.2 pp [+1.4, +26.2], pLDDT −12.4 [−22.7, −2.9].
- β versus baseline: sheet −12.1 pp [−26.7, +3.1]; β enrichment is not established.
- Mixed versus β: sheet +16.6 pp [+7.5, +25.8], coil +20.7 pp [+7.7, +31.9].
- Mixed versus baseline (additional exploratory contrast): sheet +4.5 pp
  [−10.6, +19.0], so a baseline advantage is unresolved.
- Inspection versus β: sheet +1.1 pp [−0.4, +3.6], coil −2.0 pp [−4.7, 0.0],
  pLDDT +1.4 [0.0, +3.4]. Only trajectories 1 and 2 refined, once each; all
  ten accepted, and the other eight reproduced the β control metrics exactly.

## Decision and rationale

Report the complete core comparison now and defer ranking additional controls
until their paired cohorts finish. Mixed increases sheet relative to β-only
with a substantial coil tradeoff. The β prior and current inspection criterion
do not demonstrate reliable β enrichment. Inspection screens long uncertain
coil, without a sheet-fraction eligibility target. No setting is promoted.

## Reproduce

```bash
MPLCONFIGDIR=/private/tmp/iprotein-monomer-interim-matplotlib "$NANOHUNTER_ROOT/venvs/NanoHunter_protenix/bin/python" Validation/experiments/monomer_secondary_structure_interim_v1/analyze.py
```

Set `NANOHUNTER_ROOT` to the managed runtime. Analysis creates a new timestamped
snapshot, so a later run may include more audited cohorts. This report is
`Validation/output/monomer_secondary_structure_v1/interim/20260905T234625Z/REPORT.md`.
Its JSON records audit hashes, analysis code hash, status snapshot and original
manifest identity `e437e995d3b66874f07ebad29f4d96b228766d6d96b1178b10aabaa21e8cedc2`.
Base commit remains `37cc95497283025191e7d2067cb35d1af9168d72` with dirty code
identified by the original manifest. Engine/checkpoint/package fingerprints and
hardware are in the original stage receipt; empty MSA, cached-MSA checksum n/a.

## Limits and what was not tested

Only ten paired trajectories, one length and predictor. Intervals are not
adjusted for multiple comparisons. Other controls have only one audited pilot
each in this snapshot, including two explicit exhaustion outcomes. Additional
in-flight cycles are not used. Coil is not a disorder diagnosis, and confidence
is not experimental folding validation. No inference settings, scheduler,
default or app code changed. No new performance claim or commit.

## Next

Let the detached campaign finish; compare sustained priors and remaining
controls using the full paired cohorts and final output audit.
