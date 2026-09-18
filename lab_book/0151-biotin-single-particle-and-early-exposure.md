---
entry: 0151
title: Test physical guidance without FK and trace exposure during diffusion
date: 2026-09-17
author: GPT-6 Codex
type: experiment
status: complete
machine: Apple M4 Max, 64 GB, macOS26.6.1
tags: [nise, boltz, resident, guidance, exposure, validation]
---

## Context

User approved the follow-up to0150: physical and pocket guidance on, FK off,
all30 frozen inputs submitted together. Also asked how early exposure failures
can be detected to avoid spending compute on doomed hallucinations.

## What was done

Version2 of the bounded replay contract runs two one-request arms: clean timing
and observed diffusion. Same original processed conformers and per-input RNG
states;3 recycles,200 steps,1 output,empty MSA,no affinity. Complete physical
bundle retained, FK disabled independently in the cached model and its recorded
hyperparameters. Contact guidance remains on. No production defaults changed.

Read installed Boltz2.2.1: recycling updates latent features; diffusion follows
recycling and supplies full coordinates. Observer compiles the installed sampler
with only one appended callback at the end of each step, records source hashes,
and never edits installed code. Save corrected denoised estimates and noisy states
at step1 and every5 steps. Final-state equality is mandatory. Exposure is measured
after inference using the unchanged production atom filter, not in the GPU loop.
No candidates killed: eventual outcomes are needed to measure false rejection.

## Results

Two observer insertion tests pass, including numerical and RNG
preservation plus changed-sampler rejection. The real-torch/MPS RNG and preflight
tests pass (2 tests), including the new version-2 guidance and trace constraints.
The retrospective policy test passes, explicitly identifying a recovering
candidate as a false rejection and checking the first persistence trigger.
`swift build` passes. Logs are under artifacts/0151-biotin-single-particle.

Pilot `job-4e24c9760222` completed all four folds and saved all 41 snapshots per
traced input. Its output audit correctly failed: sampler FK was off, confirmed
at each traced sample call, but Lightning logged `hparams_initial` with FK on.
Updating mutable `hparams` alone was insufficient. Fixed with the public
`save_hyperparameters` method before inference, and launched a fresh immutable
pilot `job-d6800e2b6e42`; its saved hparams now show FK off. First pilot retained
unchanged and excluded from all benchmark conclusions.

Initial local test/build attempts lacked managed Numba/compiler cache access;
reruns with the required cache access passed. Overview lookup confirms that
private validation outputs are not in the normal scientific-run catalog, so
the experiment independently verifies receipts and structures.

Corrected pilot audit passed: 2/2 outputs in each one-request resident arm,
one model load per arm, FK-off/physical+contact-on hparams verified, all feature
hashes paired, final snapshots reproduce every PDB coordinate. Clean/traced
filter and chirality verdicts agree; maximum aligned Cα difference 0.00581 Å.
Clean request 77.0138 s for 2 inputs; traced 78.1620 s, startup 9.584/9.680 s
separate. Pilot only, not a 30-input benchmark. L000 fails exposure at step 1
but passes finally, directly demonstrating a false early rejection.

The initial analysis attempted SASA on both denoised and noisy snapshots.
FreeSASA failed spatial-grid allocation on the huge early noisy coordinate
extent. Analysis now uses corrected denoised estimates only; noisy coordinates
remain archived and the final state still verifies emitted coordinates. This
does not reinterpret an unmeasurable noisy state as an exposure failure.
Pilot audit: Validation/output/biotin_single_particle_v1/pilot2/analysis/audit.json.

Main launched 22:30 UTC: `job-1927596b1a7e`, immutable plan
`plan-1927596b1a7ee001`, digest
`1927596b1a7ee0010851770655e1371090a5f218c25a3098cfd13fd9892ec0af`.
Managed output `test2/validation_runs/biotin-single-particle-3dedc8197fecf15d`.
All 108 installed Boltz source/checkpoint fingerprints match the prior replay
plan. Budget 30 clean + 30 traced predictions, one request per arm. No competing
campaign resumed.

### Full 30-input result

Main completed, exit 0. Independent audit passed all 60 outputs, completion
receipt hashes, executed guidance/recycle/step settings, one request and one
model load per arm, all 30 paired feature/RNG records, and unchanged input order.
MPS required; only the documented SVD fallback warning appeared. All 1,230
denoised snapshots were evaluated; each final snapshot reproduces the emitted
PDB's atom identities and coordinates exactly. No affinity outputs were made.

| Measure | Original physical + FK (0150) | Pocket-only batch (0150) | Physical on, FK off |
|---|---:|---:|---:|
| Seconds per initialization, startup excluded | 48.6888 | 14.4290 | 40.2182 |
| Pocket + exposure passing | 13/30 | 11/30 | 11/30 |
| Correct biotin stereochemistry | 30/30 | 19/30 | 30/30 |
| Pocket + exposure + correct chirality | 13/30 | 7/30 | 11/30 |
| No severe protein–ligand overlaps | 30/30 | 28/30 | 30/30 |
| No severe nonlocal protein overlaps | 13/30 | 9/30 | 8/30 |
| Ligand bond diagnostic passing | 15/30 | 9/30 | 17/30 |

New clean request: 1206.5465 s / 30, startup 9.6942 s separate. Traced request:
1266.7645 s / 30 = 42.2255 s each, startup 10.4979 s. Timing on Apple M4 Max,
64 GB; one trial per arm, no randomized order. Original-to-new reduction 17.40%
also includes the original's preprocessing versus frozen preprocessing here;
do not attribute the entire reduction to FK alone. No default promoted: ligand
chemistry improved over pocket-only, but protein overlap diagnostics worsened
relative to the original physical+FK sample.

Final traced exposure: 11 pass, 19 fail. A check at step 100 would reject 9/11
eventual passers, despite catching all 19 failures. At step 150: 14 failures
caught and 2 passers incorrectly rejected; step 175: 18 and 1 respectively.
The earliest sampled single check with no false rejection is step 155 (18/19
failures caught), but later transient reversals still occur.

Among the tested persistence rules, start at step 150, require 3 consecutive
failed checks spaced 5 steps apart: all 19 eventual failures detected, 0/11
passers lost, hypothetical exits at steps 160–190. This removes 11.33% of all
diffusion steps, corresponding to 9.22% gross remaining traced model time.
These are retrospective opportunities, not measured speedups; live SASA cost,
GPU synchronization and independent validation remain untested. Thresholds were
selected on the same small sample; zero observed false rejections is not proof
of safety. No early-kill behavior was enabled.

Clean/traced exposure and chirality verdicts agree for all 30. Coordinates are
not bitwise-identical: median/max aligned Cα RMSD 0.00059/0.18819 Å, median/max
protein-aligned ligand RMSD 0.00090/1.07242 Å. The outlier is L015; its exposure
failure verdict is unchanged. Do not describe tracing as numerically identical.

Artifacts: `Validation/output/biotin_single_particle_v1/main/analysis/`
contains REPORT.md, audit.json, rows.csv, trace_rows.csv, snapshot PDBs, and
overview.svg/png. Source and analysis checksums retained. Original campaign
job-002ee4e5c61e remains cancelled/paused (exit130), checkpoints preserved.

## Decision and rationale

Separate clean timing from snapshots, and observe all candidates to completion.
A transiently buried linker end may later recover; a post-hoc promising gate
cannot be silently promoted on one small ligand-specific sample.

## Reproduce

Validation/experiments/biotin_single_particle_v1/manifest.json and prepare.py;
all inference through the immutable broker plan and shared GPU lock.
Source replay job-1fdba14287be. Original full campaign remains paused.

## Limits and what was not tested

One ligand,30 X-containing initial structures. No early killing, optimization,
affinity or production default change. No independent early-stop validation,
live termination timing, restart/cancellation test of the new observer, or
long memory soak. No coordinate-based exposure check is available during
ordinary recycling without adding a separate structure prediction.

## Next

Keep physical guidance in the evaluation. FK-off is a measured tradeoff,
not an overall quality upgrade in this small initialization sample. If early
rejection is pursued, validate the late persistence rule on an independent set
and measure real filter/termination overhead before enabling it. Keep the
original campaign paused for review.
