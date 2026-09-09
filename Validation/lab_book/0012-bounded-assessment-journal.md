---
entry: 0012
title: Preserve bounded assessment attempts and explicit progression decisions
date: 2026-09-05
author: gpt-6
type: implementation
status: assessment journal complete; adaptive generation unimplemented
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1
tags: [reproducibility, recovery, validation]
---

## Context

The user requested adaptive cycle-00 remasking and automatic progression, clarifying
that it should be a generic protein-generation control. Work follows entry0093.
The adaptive sequence-generation component remains outside the work completed
here in the current toxin-associated campaign; the safe scope is a generic
assessment journal and progression decisions tested on opaque synthetic artifacts.

## What was done

Added attempt_journal.py and test_attempt_journal.py under
Validation/experiments/secondary_structure_coil_v1/. Each caller-supplied artifact
and assessment is preserved in a separate atomically published attempt directory.
Receipts hash artifacts and assessments and record the original budget policy.
Resume verifies history continuity, file integrity and an unchanged budget.
The status distinguishes awaiting_assessment, eligible and budget_exhausted.
Exhaustion never counts as a pass; subsequent attempts after eligibility fail.
No candidate generator, sequence remasking, biological weighting or scientific-job
launch is included. README explicitly records that distinction.

## Results

Eight new lifecycle tests and all 28 local tests passed. Tests exercise real
filesystem operations, reconstructed journal instances, altered artifacts,
changed budgets, history gaps, invalid/NaN assessments and a simulated failed
atomic publication. git diff --check passed. No performance measurements or
scientific inference were performed.

## Decision and rationale

Keep eligibility separate from stage execution so a recorded decision cannot
silently launch an unimplemented scientific operation. Preserve originals and
failed attempts and use the initial attempt within the declared total budget.
A terminal failure remains visible rather than selecting a different successful
subset. Caller-supplied eligibility is not a validated biological quality claim.

## Reproduce

```bash
MPLCONFIGDIR=/private/tmp/iproteinstudio-mpl ~/.iproteinstudio/venvs/NanoHunter_protenix/bin/python -m unittest discover -s Validation/experiments/secondary_structure_coil_v1 -p 'test_*.py'
```

## Limits and what was not tested

No adaptive sequence generation, region remasking, new thresholds, prediction
jobs, automatic optimization progression or application UI integration. Synthetic
artifact tests are software validation only. No power-loss testing, new hardware
benchmark, app build or commit. Existing runtime, models and raw predictions were
not changed.

## Next

The journal can support safe assessment workflows. The requested complete adaptive
protein-generation feature remains unimplemented; do not describe this component
as an operational remasking or cycling control.
