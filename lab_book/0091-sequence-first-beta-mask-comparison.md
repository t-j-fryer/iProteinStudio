---
entry: 0091
title: Test complete patterned sequences before the 50 percent X mask
date: 2026-09-05
author: gpt-6
type: experiment
status: complete; analyzed in project0092 and Validation0010
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [secondary-structure, initialization, boltz, reproducibility]
---

## Context

The user requested two seed-only arms: stronger patterned beta sampling, alone or
with existing helix-kill weights, followed by a 50% X mask. Each full arm has ten
90-residue trajectories and five optimized cycles with Boltz2. This supersedes
the unsubmitted sustained-prior confirmation01 proposal; no such job was launched.
No binder structure is supplied. The existing bundled target/MSA is unchanged.

## What was done

Added opt-in `--seed-sampling-order sample-then-mask` to the helper, runner and
immutable MCP preflight. Existing mask-first replay streams/defaults remain.
The complete amino-acid sequence is sampled first, including the local i-4
helix-kill rule; an independent deterministic mask then hides45/90 residues.
Saved plans retain the full sequence, mask positions, masked sequence and
algorithm identifier. Beta and mixed arms share architecture/mask seeds.
Active secondary-prior plans now include the helper in script provenance.

Declared config, broker driver, locked two-file runtime staging and audit live in
`Validation/experiments/secondary_structure_seed_mask_v1/`. Raw output is ignored
under the corresponding `Validation/output/` directory. Staging retains previous
runner/helper copies and fingerprints the installed Boltz2 and SolubleMPNN weights.
No environments, weights, cache or completed scientific outputs are changed.

## Results

Implementation tests:7 helper tests,16 MCP tests, CLI contract including actual
runner-to-helper invocation, and10 audit integrity tests passed. MCP loopback test
required approved local socket access. No new folding results at declaration.

## Decision and rationale

Beta and pattern strengths1.0 (previous experiment0.5); turn strength remains0.5.
Mixed adds helix-kill0.5; beta-only anti strength0. Later MPNN has no prior.
Use one smoke trajectory per arm, then ten per arm only after operational audits.
The full first seed repeats the smoke; smoke is not an independent replicate.
Primary comparison is paired mixed minus beta; average cycles01-05 within each
trajectory first. Report PSEA H/S/C, confidence, interface and sequence complexity.
Sheet>=25% and helix<40% remain descriptive cohort targets, not a smoke efficacy gate.
Historical controls are descriptive because order/strength changed. No selection
of successful cycles or structures, no defaults promoted.

## Reproduce

From the canonical repository, with the managed runtime already installed:

```bash
python3 Validation/experiments/secondary_structure_seed_mask_v1/stage.py
python3 Validation/experiments/secondary_structure_seed_mask_v1/campaign.py prepare --phase smoke
python3 Validation/experiments/secondary_structure_seed_mask_v1/campaign.py start --phase smoke
python3 Validation/experiments/secondary_structure_seed_mask_v1/campaign.py status --phase smoke
# After completed jobs, run audit.py using the managed Protenix scientific Python.
# Then prepare/start/status --phase full and audit --phase full.
```

Manifest records exact commit, dirty diff/untracked hashes, inputs and immutable
plan digests. Stage receipt records measured hardware/OS and before/after hashes.

## Limits and what was not tested

No independent complex or binder-alone checks, no experimental binding/function,
no other targets, lengths, hardware or predictors. No aggregate formation assay.
PSEA reports predicted coordinate assignment, not experimental secondary structure.
No app UI change, full app build or commit in this experiment.

## Next

Launch and audit smoke, then run and audit both full10 arms. Append job identities,
failures and final measurements here and in Validation entry0009.

## Launch record

Smoke plans reviewed and launched through the shared broker on2026-09-05:

- beta_seed_only: `job-42e034cce637`.
- mixed_seed_only: `job-900a236120fc`.

Stage receipt measured Apple M4 Max,68,719,476,736bytes RAM, macOS26.6.1.
The beta-only plan saves the inactive anti-strength default0.5; beta mode applies
zero anti pressure and the MCP forbids an anti-strength flag in that mode.

## Full campaigns submitted after smoke audit

Both smoke arms completed and passed12/12 coordinate/sequence/confidence checks,
including exact full-plan replay,45X/90, paired identical masks and zero secondary
bias in the five MPNN redesigns. The documented Boltz SVD CPU fallback is audited;
Biotite label_atom_id substitution is a mmCIF field-name fallback, not CPU inference.

Full plans differed from smoke only by1→10 trajectories and output/run names.
Immutable input and scientific script hashes matched. Submitted jobs:

- beta_seed_only: `job-a29994816133`.
- mixed_seed_only: `job-5c17a5cfae6d`.

A detached monitor was launched and observed running. It only reads submitted
job status and, after both complete, calls the read bridge results_overview, runs
the full audit and writes analysis/full/comparison.md and comparison.json. It
never submits, resumes, cancels or changes a scientific job. Progress/failures:
analysis/full/monitor_status.json; log: analysis/full/monitor.log.

Final tests:7 helper tests,16 MCP tests, actual runner/helper CLI contract,
11 audit tests and7 paired-summary tests; diff whitespace check passed.
Full measurements remain pending; no full-cohort efficacy claim yet.

Monitor review fixed SystemExit error recording and duplicate launch handling.
The corrected detached monitor acknowledged startup; an executed duplicate-launch
check preserved its PID/status. Broker status queries may refresh stale-worker
job metadata according to the existing broker policy; the monitor does not change
scientific settings or invoke launch/resume/cancel. Full jobs remain running/queued.

## Completed analysis

Both full arms completed;120/120 outputs audited and394 recorded hashes verified.
Neither cohort met the joint structural target. Full results and interpretation
are recorded in project entry0092 and Validation entry0010.
