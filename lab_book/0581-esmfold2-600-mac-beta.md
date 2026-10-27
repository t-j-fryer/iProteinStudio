---
entry: 0581
title: Establish an ESMFold2-600 Mac beta and audit memory controls
date: 2026-10-26
author: Codex
type: port
status: bounded-acceptance-complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [esmfold2, memory, mlx, beta]
---

## Context

User asked about Full on 16 GB Macs, chunking, and installing Synthyra ESMFold2-600 as a Mac beta. The smaller checkpoint is a distinct 24-block, sequence-only model with a 600M encoder and Synthyra-adapted confidence head. It must never substitute for Full/MSA-conditioned inference silently.

## What was done

Inspect pinned upstream model/configuration/tensor metadata and the existing MLX port before any remote-code execution or model loading. Work in `.worktrees/esmfold2-600-beta`. Validation 0261 declares bounded monomer acceptance, explicit settings, strict loading, memory accounting and replay. Existing production environments remain immutable.

## Results

Bounded software acceptance completed; broader Figure 2a testing is declared separately in0582. Existing Full process-tree footprint anchors in `memory_profiles.json` are 20.249993 GiB at 96 tokens and 45.402259 GiB at 916 tokens, n=5 each, from the recorded M4 Max/64 GB qualification; these are accounted footprint, not exact physical RAM. The MLX port exposes transition chunking but Studio currently leaves it unset and permits a 4 GiB allocator cache. Weight memory remains separate.

## Decision and rationale

Reuse the validated MLX model, feature/decode helpers and managed execution contracts where tensor and architectural equivalence can be checked. Keep the beta explicit, sequence-only and outside default workflows. CUDA-only FastPLMs kernels and H100 measurements do not establish Mac performance.

## Reproduce

See `Validation/experiments/esmfold2_600_beta_v1/manifest.json`; immutable source metadata lives under `Validation/output/esmfold2_600_beta_v1/upstream`.

## Limits and what was not tested

No actual16 GB hardware, binding efficacy, confidence calibration or whole-model CUDA parity. No interrupted-inference cancellation test; completed submission idempotence was checked. No GUI selector/public release/default replacement. Four-target resident benchmarking is separate in0582.

## Measured bounded acceptance

Same96-aa SUMO monomer, seed 42, one sample, 3 loops/50 requested steps, empty MSA,
cache 512 MiB. One fresh process per row, M4 Max40-core GPU/64 GB/macOS26.6.1.

| Engine | Transition chunk | Synchronized model call (s) | Sampled accounted tree footprint (GiB) | MLX peak allocation after loading (GiB) |
| --- | ---: | ---: | ---: | ---: |
| 600 beta | 0 | 0.937 | 5.070 | 3.533 |
| 600 beta | 32 | 1.002 | 5.032 | 3.579 |
| Full | 0 | 2.060 | 17.573 | 14.667 |
| Full | 32 | 1.901 | 17.246 | 14.636 |
| 600 beta, final scoring/provenance correction | 32 | 0.916 | 5.324 | 3.579 |

These n=1 conditions do not establish statistical speedups or16 GB compatibility.
Model-call time excludes loading/features/decoding; sampled footprint can count
shared pages multiple times and is not exact physical RAM. MLX is a separate
allocator measure and must not be added to process memory. All five outputs
passed exact96-residue/776-atom, chain, finite coordinate/confidence/cardinality
audits. Original files and per-run memory traces remain immutable.

All 913folding and 368encoder tensors load strictly. CPU synthetic confidence
arithmetic passed at2e-5 tolerance after explicitly matching the existing MLX
BF16 trunk input boundary; largest observed head error was3.815e-6 for PAE.
This is a zero-block head oracle, not whole-model parity. The initial test
failed because the CPU reference retainedFP32 through its empty trunk; the
failure log is retained, no tolerance was loosened. Initial shape checks also
caught release-only PARCAE/LM/confidence layers and were corrected to the pinned
experimental architecture before inference. No remote Python was executed.

Beta contract tests5, profiles10, adapter8, installer6, engine-safety4,
memory-admission27 and MCP bridge24 passed. Swift build passed. Initial
system/control Python test attempts lackedYAML; the installed engine interpreter
was then used. Sandbox-only bridge tests lacked macOS memory readings; host rerun
passed24. A sandbox Swift attempt could not access Xcode module caches; host
build passed. Those failures were environmental, not counted as successful tests.

Completed submission replay returned the same job without inference; all 21 saved
file hashes and mtimes were unchanged. Managed job IDs: chunk32`job-3ffe0006b5d3`,
chunk0`job-d80186e6e8a6`, Full0`job-4bd20bb9d3d4`, Full32`job-fa2d47628db8`,
final beta`job-6f39b242edaa`. Plans, runtime/code snapshots, auditJSON, memory traces,
installation receipt and pinned upstream metadata are under
`Validation/output/esmfold2_600_beta_v1/`. Initial base commit0295016; each plan
records the exact dirty-worktree code snapshot instead of claiming a clean commit.

Install succeeded with the unchanged immutable ESMFold2 runtime and independent
verified600assets; no6B weights are dependencies of the new component. Bridge47
exposes opt-in prediction only. Beta defaults retain upstream unchunked transitions
and use512 MiB cache; Full/Fast defaults remain unchanged. Monomers rank by pTM;
experimental confidence is explicitly labelled uncalibrated. Protocol does not
promote broader memory estimates. The subsequent Figure 2a benchmark completed; campaign restoration is recorded
in0582.

The paired600chunk0/chunk32 CIFs were byte-identical for the96-residue control.
Full CIFs differed, so no Full chunk-equivalence claim is made. Fresh empty-root
600-only installation was not rerun; dependency-selection tests and the verified
existing-runtime installation establish the current installer scope. Cache
overrides are limited to0–4096 MiB, avoiding increases above the calibrated
Full/Fast default cache allowance.
