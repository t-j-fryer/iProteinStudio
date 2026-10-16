---
entry: 0430
title: Qualify LASErMPNN CPU residency and audit affinity cost
date: 2026-10-15
author: Codex
type: experiment
status: complete
machine: Apple M4 Max 40-core GPU, 64 GB unified memory
tags: [biotin, lasermpnn, cpu, residency, affinity]
---

## Context and protocol

User authorized LASErMPNN tests and efficient CPU/GPU orchestration before the
matched biotin experiment. Added a bounded CPU-only qualification under
Validation/experiments/lasermpnn_residency_v1. Four saved prepared biotin complexes,
one/five samples, two alternating repetitions of fresh processes and resident
1/2/4-worker pools, plus two workers with two native threads. Expected240 sequences.
All calls retain upstream run_inference; only model loading is cached. Reset
Python/NumPy/Torch RNG after model load to compare fresh and resident requests.
Historical NISE ignored that seed; no retrospective reproducibility claim.

## Measurements and verification

Pending managed execution. Complete FASTA bytes including scores must agree;
timings include import/load/pool teardown. Record worker RSS, request spans and
load times. Immutable manifest, source/weight/input fingerprints and shared Studio
execution lease required. No main100+100 backbone experiment started.

## CPU/GPU design decisions

Use persistent bounded CPU queues rather than maximising thread count blindly.
Existing eight-worker linker geometry pool remains reusable. Prior0422 measured
reporting pools slower than one process for small batches; preserve that result.
CPU preparation for independent lineages can run while GPU predicts other inputs,
with bounded prefetch and atomic per-unit checkpoints. Same-lineage dependencies
must wait for their predicted structure. Actual overlap throughput needs a separate
end-to-end qualification, not inferred from this isolated CPU test.

## Affinity audit

Inspect installed Boltz main.py, model/models/boltz2.py and inferencev2.py plus
Studio resident_predictor.py. Structure and affinity have distinct cached weights.
Affinity consumes saved full-precision pre_affinity coordinates, affinity-specific
cropping/features, five recycles, its own sampling settings and two output branches.
Do not confuse skipping the outer structure stage with proving no internal affinity
diffusion. Check checkpoint hyperparameters before any optimization claim.

## Limits

No upstream package modification, scientific budget reduction, app release or
production promotion. This short prepared-input test excludes protonation/conversion,
CPU/GPU overlap, long memory soak and interruption/resume qualification.

## Submission and source audit

Prepared immutable plan1b40ef9e51ca8266, SHA256
1b40ef9e51ca82663b77ea91e7bb7d78ef2b4bed269c53edcc9f0a132b3ed3e4;
job-1b40ef9e51ca queued behind active job-16b8e7b9d87d. Output:
`Validation/output/lasermpnn_residency_v1/20261015T230737Z`.
No current work interrupted. Source HEAD25b3eb92dae59b4f4e48f3f10f7d6b8607faeb3d;
unrelated dirty files preserved, exact benchmark/upstream scripts fingerprinted.
Four executed CPU contract tests pass: output cardinality/alphabet, per-call RNG
reset and restoration of the upstream loader/argv on failure. These tests do NOT
establish neural equivalence or throughput; those await the queued experiment.

Read-only checkpoint metadata confirms affinity `skip_run_structure=false`,
`run_trunk_and_structure=true`, confidence enabled, affinity enabled and ensemble
enabled. Native CLI defaults are sampling_steps_affinity200 and
diffusion_samples_affinity5 (the Python callback signature misleadingly says3;
the actual Click CLI supplies5). Native affinity execution fixes5recycles and
disables physical/contact/FK steering in its own internal inference. Structure
potentials remain on as requested. Affinity cropping uses saved pre_affinity
coordinates and at most256tokens/2048atoms/200protein tokens. It then runs its
own trunk, diffusion, confidence selection and two affinity output branches.
Thus previous phrasing 'without refolding' refers only to bypassing the outer
structure call: it does not imply no internal affinity-model diffusion. The
35s/17s worker/aggregate timing in0429 is observed and unaffected by correcting
this explanation. Do not infer savings by merely reducing structure steps.

Primary source checked against installed code:
https://raw.githubusercontent.com/jwohlwend/boltz/main/src/boltz/main.py
and src/boltz/data/crop/affinity.py. Installed checkpoint/CLI inspection saved in
`lab_book/artifacts/0430-lasermpnn-affinity/affinity_inspection.json`.

Candidate subsequent affinity experiments (not launched or promoted): hold saved
inputs fixed, compare200steps/5samples with100/5,50/5 and200/1, then combined50/1
if promising. Preserve five recycles, ensemble, and all chemistry initially;
measure per-candidate P(bind) shifts, rank/threshold/top-set stability, repeat-seed
variation and total resident elapsed time. Smaller crops, reduced ensemble and
reuse of structural-model trunk activations are not approved shortcuts.

## Completed CPU qualification (2026-10-15)

Watcher released the previous owner at23:37:58UTC; managed test started23:38:04.
All240 sampled sequences AND FASTA scores match exactly, zero mismatches.
Observed elapsed seconds for the same24-sequence workload, repetitions0/1:
fresh48.27/46.58; resident1CPU12.21/12.24; resident2CPU9.21/9.14;
resident4CPU7.99/8.20; resident2CPU with2threads8.59/8.59.
Timings include process imports, model load, sampling and pool teardown.
Hardware M4Max64GB. This demonstrates prepared-input CPU residency savings,
not full-cycle throughput; no production promotion. Geometry/GPU overlap follow-up
is0432/Validation0195. Immutable results.json contains per-request timings/RSS.
