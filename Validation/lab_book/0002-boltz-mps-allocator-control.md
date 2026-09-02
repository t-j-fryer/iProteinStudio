---
entry: 0002
title: Control the Boltz MPS allocator boundary on M4
date: 2026-09-01
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
---

## Question

Does the build-9 pre-batch `torch.mps.empty_cache()` boundary alter Boltz-2
speed, cardinality, confidence or structure on the M4 Max relative to the
otherwise identical build-8 FP32 launcher?

## Design

Three fresh processes per arm, interleaved A-B-B-A-A-B. Sequence, YAML, exact
cached MSA, Boltz 2.2.1 checkpoint/cache, PyTorch 2.13.0, seed 42, one diffusion
sample, default recycles/sampling steps and output format are held constant.
Each run must produce exactly one CIF and confidence JSON, report MPS, pass the
shared geometry validator and use no CPU fallback except Boltz's documented
`linalg_svd` alignment operation.

## Results

All 6/6 runs passed cardinality, MPS, geometry and fallback audits. Every run
produced the same structure SHA-256 (`f3a132c572d3…`), pTM
(`0.8701755404472351`) and complex pLDDT (`0.907027542591095`). The aligned
Cα RMSD of every candidate and repeated control to the first control was
approximately `5.45e-15 Å`, numerical zero.

| Launcher | n | Full wall time, mean ± SD | Median | Model progress | Result |
|---|---:|---:|---:|---:|---|
| Build-8 FP32 control | 3 | 16.604 ± 0.706 s | 16.253 s | 4 s each | pass |
| Build-9 FP32 + reset | 3 | 16.039 ± 0.127 s | 15.988 s | 4 s each | pass |

The nominal 0.565-second candidate advantage is not promoted as a speedup: the
first control was the coldest run and n=3 is intentionally small. The defensible
result is no detected M4 penalty. Each run contained exactly the one documented
Boltz `linalg_svd` CPU fallback and no other fallback.

The exact MSA SHA-256 was
`377a3af41f6816683c9b06241fafd2e0c2bc6b0129c2f4a78387ad36f75f34cf`.
Raw commands, wrapper hashes and per-run values are in the ignored immutable
`Validation/output/boltz_mps_allocator_v1/manifest.json`; `audit.json` passes.

## Decision

Retain the reset for the M1 acceptance build. On this short M4 fold it neither
shortcuts inference nor changes output and has no detected performance cost.
This experiment cannot establish that the reset repairs the affected M1 Pro,
nor does it clear the setting for long multi-input or resident campaigns.

## Inputs and reproduction

See `Validation/experiments/boltz_mps_allocator_v1/README.md`. The generated
ignored `Validation/output/boltz_mps_allocator_v1/manifest.json` records exact
commands and SHA-256 fingerprints before compute.

## Limits

One short monomer and one seed are intentionally used to isolate launcher
behavior. Multimers, ligands, longer sequences, multiple samples, memory soak
and the affected M1 Pro remain untested here.
