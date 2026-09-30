---
entry: 0231
title: Reconstruct upstream and optimized Mac prediction baselines
date: 2026-09-30
author: Codex
type: audit
status: complete
machine: Source and installed metadata audit on Apple M4 Max, 40-core GPU, 64 GB, macOS 26.6.1
tags: [predictors, provenance, performance, paper]
---

## Context

User requests research for a paper figure comparing original Mac execution before our interventions with the current implementation. Explicitly permits historical read-only inspection of iProteinHunter-beta, NanoHunterStudio, NanoHunter and iProteinHunter. No new predictions requested; ongoing paper campaign must continue.

## What was done

Reviewed historical worktrees, canonical Lab Books, installed source/metadata, patch files, installer pins and active campaign configuration. Consulted primary upstream Boltz, Protenix, IntelliFold, OpenFold, Biohub ESM and community MLX sources online. Read Validation instructions. Created `Validation/experiments/mac_intervention_baselines_v1/{RESEARCH.md,manifest.json,evidence.json}` and Validation entry0063.

## Results

No new measurements — research only. Historical measurements in the report are explicitly attributed to entries0228/0229/0230/0211 and their hardware/workloads. The nine-model protocol separates author-stock feasibility, minimally correct Mac/community-port performance and qualified Studio optimizations. CPU-to-GPU, community-backend and implementation-only contrasts are distinct. Stock failure has no numerical speed ratio.

Installed metadata: Boltz/IntelliFold Torch2.14.0; Protenix/Constraint2.7.1; OpenFold2.6.0 with MLX0.32.0; ESM supporting Torch2.11.0 and MLX0.32.2. Exact-token sizing is in app source; the latest CCD/residency/loader/diffusion-cache/free-cache optimizations are isolated campaign hooks. Do not describe those as released. Historical repos are already modified Mac implementations. Public IntelliFold README describes JAX while the pinned packaged PyTorch runner remains present, requiring source-level reconstruction.

## Decision and rationale

Recommend capability/attribution, paired cold/resident time+memory, and quality panels. Preserve native directory reuse in upstream controls. Hold scientific inputs and budgets constant per contrast; reduced steps and different checkpoints are separate scientific comparisons. SUMO core21–96 is the target structural reference. Do not attribute community MLX kernels to Studio, count failed-fidelity optimizations as gains, or multiply unrelated historical speed ratios.

## Reproduce

Read RESEARCH.md and machine-readable research manifest. evidence.json records source hashes, repository HEADs/dirty tracked counts, installed package metadata and runtime-manifest hashes without importing numerical libraries. Rehash those files to audit the snapshot. Existing campaign frozen asset fingerprints provide checkpoint provenance without copying weights.

## Limits and what was not tested

No inference, installs, GPU imports, job changes, app edits, publication or fresh-Mac test. Missing clean baseline environment locks, original-author OpenFold ancestor, pinned IntelliFold archive reconstruction and final representative-panel selection remain explicit prerequisites for execution, not hidden completed tasks. No claim of universally failing stock installs. No Swift build because no code change/commit. Preserve unrelated dirty work and existing raw results.

## Next

When requested, freeze runnable baseline environments/patch stacks and paired workload manifest; then execute through immutable broker plans after the current campaign. Do not run this research manifest directly.
