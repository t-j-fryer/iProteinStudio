---
entry: 0582
title: Benchmark ESMFold2-600 on the Figure 2a structures
date: 2026-10-26
author: Codex
type: benchmark
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [esmfold2, memory, prediction, figure2a]
---

## Context

The user requested all Figure 2a structures in the existing benchmark setup with
ESMFold2-600, recording timing and memory. This extends the bounded monomer port
in 0581. Original production jobs remain paused under the prior authorization.

## Declared protocol

See `Validation/experiments/esmfold2_600_figure2a_v1/protocol.json` and Validation 0262.
Exact SUMO96, T4lysozyme164, MBP370 and citrate synthase2×458 constructs/masks.
One warmup then seeds 42–46, one sample, 3 loops/50 requested steps, one resident model
per block. Primary cache4096 MiB/chunk0 matches the historical benchmark's allocator
policy; separately labelled low-memory cache 512 MiB/chunk32 changes both controls.
Eight serial blocks,40 measured outputs plus8 warmups. No MSAs:600M has no MSA encoder.
The dimer is an explicit research benchmark, not general app complex promotion.

Reuse unchanged Figure 2a synchronized profiler,0.5 s process-tree footprint/RSS
sampler, fixed crystal masks, assembly-permutation and geometry audit. Retain
cold loading, warmup, request/stage timing, CPU time, allocator counters, whole-
system swap and host-load observations separately. Do not sum nested stage times
or memory counters. Seeds within one resident session are not independent cold runs.

## Results

Completed 40 measured predictions and 8 warmups across all eight resident blocks.
No 16 GB hardware was tested.

## Reproduce and limits

Prepare the new experiment, then start its immutable plan through Studio's broker.
No direct GPU workers; runtime/code/asset fingerprints and memory override retained.
Raw failures and incomplete attempts are preserved; resumed units require matching
hashes. No default promotion, figure replacement, accuracy equivalence or public
release is authorized by this benchmark. Production jobs will resume after testing.

## Retained first attempt

Plan`plan-0e964794ce8e8bb9`/job`job-0e964794ce8e` was cancelled after
worker logs showed an explicit `env NANOHUNTER_ROOT=...` argument overrode the
broker's frozen runtime view. SUMO outputs are diagnostic only, excluded from
qualification. Original output directory remains immutable. Removed that
assignment and added a fail-closed runtime-view/bindings check before loading.
The corrected plan uses a fresh`esmfold2_600_figure2a_v1_retry2` output directory.

## Completed measurements

Corrected plan `plan-e0bb253783431482`, digest
`e0bb253783431482c120a91d7c46bf66fa728a300630e744578f252f03d5782b`,
job `job-e0bb25378343`. Runtime view and adapter SHA are recorded in every
block's `load.json`; the plan retains the exact runtime/code snapshot. Model
revisions and architecture are those recorded in 0581. The first attempt remains
excluded; the corrected run completed without failures or automatic setting changes.

| Target | Arm | n | Mean request s ± SD | Mean request-peak footprint GiB ± SD | Whole-session peak footprint GiB | Mean CA RMSD Å |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| smt3 | figure2a | 5 | 0.798 ± 0.004 | 7.537 ± 0.000 | 7.537 | 2.248 |
| smt3 | low_memory | 5 | 0.870 ± 0.004 | 6.194 ± 0.658 | 6.593 | 2.248 |
| t4_lysozyme | figure2a | 5 | 1.632 ± 0.042 | 8.119 ± 0.001 | 8.119 | 0.420 |
| t4_lysozyme | low_memory | 5 | 1.736 ± 0.056 | 6.416 ± 0.026 | 6.514 | 0.420 |
| mbp | figure2a | 5 | 9.179 ± 1.551 | 10.728 ± 0.434 | 11.125 | 0.580 |
| mbp | low_memory | 5 | 13.467 ± 0.701 | 7.005 ± 0.261 | 7.313 | 0.580 |
| citrate_synthase | figure2a | 5 | 76.007 ± 2.308 | 28.296 ± 0.008 | 28.306 | 2.500 |
| citrate_synthase | low_memory | 5 | 84.509 ± 0.464 | 17.292 ± 0.294 | 18.018 | 2.500 |

Times are warmed resident requests including feature preparation, prediction,
decoding/writing; cold loading is separate (7.52–8.05 s for these blocks).
The footprint columns are Darwin process-tree accounted memory, not exact physical
RAM. Per-request values use the original 0.5 s sampler; short requests can have
only one sample, and sampled peaks are lower bounds. Whole-session peaks also
include loading, warmup and audits. MLX allocator counters are separate: mean
request peaks for the dimer were24.572 GiB standard and18.572 GiB low-memory.
Never add allocator and footprint values. The low-memory arm changes both
chunking and cache limit, so this does not isolate either control's effect.

All 48 outputs passed exact sequence/chain/cardinality, complete backbone and
finite coordinates/confidence checks. The final audit verified 288 receipt-listed
files. Every block retained one model identity for warmup and all five seeds.
Host audit:243 samples, zero compiler samples, no monitor errors; longest external
CPU≥200% episode was one sample (threshold: three consecutive 5 s samples).
Timing passed the declared host gate; ordinary desktop/GPU/thermal interference
is not excluded. Seeds within one resident session are not independent cold starts.

All five SUMO, MBP and dimer paired structures were byte-identical between arms.
T4 files differed; aggregate reference RMSD was the same to three decimals,
without a blanket numerical-equivalence claim. These are training-era reference
agreement checks, not blind generalization, confidence calibration or binding
validation. No app default or memory-admission profile was promoted; the general
600 beta app/CLI route remains complete monomers only. Dimer results are explicitly
research-only. No public release or manuscript figure replacement was performed.

## Export and reproducibility

`Validation/output/esmfold2_600_figure2a_v1_retry2/analysis/` contains
`measurements.csv` (all 48rows, warmup flag), `summary.json`, and `REPORT.md`.
Raw per-seed measurements include nested stage timers, CPU time, RSS, MLX
allocations/cache, whole-system swap, confidence, domain/assembly RMSD and CA-lDDT,
interface contact metrics, geometry outcomes and source receipts. Source hashes
and the frozen target file establish the original Figure 2a constructs/masks.
The reported MSA policy is explicitly empty; the600M architecture has no MSA encoder.

Executed the CPU protocol tests: 3, all40 + 8 managed requests, receipt analysis and
idempotent beta submission checks from 0581. App/regression checks are recorded
in 0581. No actual16 GB machine, interrupted mid-unit recovery on the corrected
benchmark, large-cohort memory soak or CUDA numerical parity was tested.
The cancelled first attempt exercised managed stop before the corrected run.

Final checks passed: Swift build, 24 MCP bridge tests, 5 beta contract tests,
bridge47 doctor and verified600component detection. The installed beta remains
CLI/MCP opt-in; no native selector or public release was added. Intended source
files were mirrored into the canonical repository, merging only new Lab Book
index entries and preserving unrelated local edits.

Queue restored: `job-ae5e53a4beb8` is running and `job-1e0a8a779e14` is queued.
Their original plan digests are unchanged. Restoration/status receipts are in
`analysis/../delivery/`; no completed production artifacts were changed.
