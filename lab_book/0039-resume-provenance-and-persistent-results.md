---
entry: 0039
title: Make iterative resume, score provenance and partial results explicit
date: 2026-08-26
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [iterative-design, resume, provenance, results, ui, boltz]
---

## Context

Iterative campaigns already wrote per-cycle checkpoints and a durable
`studio_run.json`, but the explicit Activity **Resume** action could replay a
manifest created with the form's optional resume toggle off. The persistent results
browser also depended on `comparison_scores_long.csv`, which is finalized only after
the complete design and post-prediction campaign succeeds. This made valid structures
from stopped runs appear unavailable and made it too easy to confuse the design
engine's self-score with an independent check. Hotspot input also collapsed the
design-engine menu to Boltz instead of explaining the capability boundary.

## What was done

- Added one operational resume contract: explicit Resume and Retry preserve every
  recorded scientific argument, remove duplicate resume flags and add exactly one
  `--resume`. An unreadable launch manifest now fails visibly.
- Made Activity expose **View** whenever durable score rows exist, including failed,
  stopped and interrupted iterative campaigns.
- Made the result loader reconstruct unfinished campaigns directly from
  `run_*/metrics_per_cycle.csv` and
  `run_*/post_<predictor>/cycle_*/post_metrics_row.csv`. The final comparison table
  remains preferred when present.
- Added structured result stage and score-source fields. Persistent and live views
  now state the engine that emitted each metric, distinguish design-stage from
  independent post-prediction scores, restore the recorded hit threshold, and show
  separate design-stage and post-check hit counts.
- Kept protein hotspot selections saved but dormant for Protenix or IntelliFold.
  These engines now remain selectable and run against the full target complex;
  hotspot YAML and Boltz potentials are emitted only when Boltz is the design engine.
  Atom-specific ligand campaigns remain Boltz-only.
- Reflowed Target Prep setup controls as vertically labelled, full-width controls so
  labels cannot be covered by their menus.

## Results

The production Boltz runner was exercised with one 40-residue random minibinder
against the shipped 71-residue alpha-cobratoxin target and its 1,148-record MSA. The
campaign contained cycle 00 and one optimisation cycle. The identical command was
then repeated with `--resume`.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Initial campaign | 1 campaign | runner duration | 44.260725 s |
| Initial cycle 00 | 1 fold | fold duration | 22.412475 s |
| Initial cycle 01 | 1 fold | fold duration | 19.302319 s |
| Resumed campaign | 1 campaign | runner duration | 0.162353 s |
| Resumed invocation | 1 invocation | total wall time including startup/preflight | 0.50 s |

The resumed log explicitly reported cycles 00–01 already predicted, reused both
predictions and the recorded redesign, and launched no new fold. Swift contracts also
reopened an interrupted fixture containing a Protenix-v2 design score and an
IntelliFold post-check score without a final comparison table.

## Decision and rationale

An explicit Resume click is stronger intent than the original form's automatic-reuse
toggle, so it always enables checkpoint reuse. Reconstructing the command from the
current project form was rejected because it could change the model, threshold, seed,
MSA policy or sampling settings after the run began.

Scores are presented as multiple observations with explicit stage and engine rather
than replacing the design score with the post-predictor score. The design score is the
quantity optimized during the loop; the post score is independent validation. Both
are scientifically useful, but only when their provenance remains visible.

Non-Boltz protein design is allowed with no epitope restraint. Silently translating a
Boltz hotspot to another engine was rejected because those backends do not implement
the same restraint. Silently switching the user's selected engine back to Boltz was
also rejected. Dormant, visibly annotated state is reversible and honest.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh

caffeinate -dimsu swiftc -parse-as-library \
  Sources/iProteinStudio/Models/ProteinSequenceInput.swift \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/DesignRequest.swift \
  Sources/iProteinStudio/Models/DesignPoint.swift \
  Sources/iProteinStudio/Core/ResumeContract.swift \
  Sources/iProteinStudio/Core/TemplateWriter.swift \
  Sources/iProteinStudio/Core/CommandBuilder.swift \
  Sources/iProteinStudio/Core/MetricsWatcher.swift \
  Tests/IterativeCommandContractHarness.swift \
  -o /private/tmp/iproteinstudio-iterative-contract
caffeinate -dimsu /private/tmp/iproteinstudio-iterative-contract

caffeinate -dimsu swiftc -parse-as-library \
  Sources/iProteinStudio/Models/RunResult.swift \
  Tests/PredictionResultsContractHarness.swift \
  -o /private/tmp/iproteinstudio-results-contract
caffeinate -dimsu /private/tmp/iproteinstudio-results-contract

caffeinate -dimsu swift build
```

The bounded GPU acceptance output is retained at
`/private/tmp/iproteinstudio-resume-acceptance/resume_acceptance_20260826` for this
machine session. Its exact runner arguments and measured output are recorded in the
working-session log that produced this entry.

## Limits and what was not tested

- The GPU acceptance resumed a fully completed two-checkpoint Boltz campaign. The
  same runner branches handle an interruption after any completed cycle, but this
  pass did not deliberately kill a process while a fold was active.
- Protenix v2, Protenix Mini and IntelliFold driver routing were covered by argument,
  YAML and result-provenance contracts; no additional GPU campaigns were spent on
  each driver in this pass.
- Target Prep was source-layout and build tested. A screenshot/Accessibility-API
  inspection of every macOS text-size setting was not performed.
- OpenFold-3 remains an independent checker, not a design driver, following the
  prior measured design-driver comparison; this change does not reverse that product
  decision.

## Next

Exercise a deliberate mid-campaign process interruption in a future release
acceptance pass and add a compact stage/engine filter if campaigns with many cycles
and several post predictors make the result list too dense.
