---
entry: 0062
title: Audit the Boltz MPS reset across Apple GPU generations
date: 2026-09-01
author: codex-gpt-5
type: experiment
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [boltz, mps, m1, m4, correctness, performance, allocator]
---

## Context

Entry 0061 reported a 4.5-second Boltz prediction interval after adding a
pre-batch MPS allocator reset. That appeared surprisingly fast and raised two
valid questions: whether the run had skipped work, and whether an M1 workaround
could slow or perturb the M4 path.

## What was done

- Distinguished Lightning's 4-second model progress interval from complete
  process wall time. The original interactive build-9 command took 18.4 seconds
  including Python startup, input processing, checkpoint load, writing and
  geometry validation.
- Added the governed `Validation/experiments/boltz_mps_allocator_v1` experiment.
  It alternated three fresh build-8 FP32 controls and three build-9 candidates
  on the exact build-8 M1 input and MSA. Seed, sample count, model defaults,
  checkpoint, runtime and output format were identical.
- Audited exit status, output cardinality, MPS selection, geometry, CPU fallback,
  confidence values, structure hashes and aligned Cα coordinates.
- Ran the minimal reproducer from PyTorch issue 193487 locally under Studio's
  exact Boltz PyTorch 2.13.0 runtime. Fresh, allocator-triggered and
  post-`empty_cache` products all had zero elements above the issue's error
  threshold and the same maximum relative error (`1.9631e-05`) on this M4 Max.
- Tested Boltz's upstream `bf16-mixed` Trainer setting on the same fold. Lightning
  2.5 announced bfloat16 but then disabled autocast because CUDA was unavailable;
  the resulting MPS output was bit-identical to explicit FP32. Thus Studio's
  FP32 setting did not change the arithmetic or explain the 4-second interval.
- Read primary issue and maintainer history rather than inferring from chip age:
  - [PyTorch 193487](https://github.com/pytorch/pytorch/issues/193487) contains
    an M4/macOS 26.6.1 non-reproduction and an M1 Pro/macOS 26.6/PyTorch 2.13
    reproduction in which `empty_cache()` exactly restores results.
  - [PyTorch 94765](https://github.com/pytorch/pytorch/issues/94765) reports the
    same `MPSNDArrayGatherND` assertion on an M1 Pro. It was later closed after
    non-reproduction on newer PyTorch/macOS for its minimal shape.
  - [PyTorch 135240](https://github.com/pytorch/pytorch/issues/135240) reproduces
    the same assertion on M3; a PyTorch maintainer identified the proper fix as
    MPS/OS-side and observed it fixed in macOS 15.2 while macOS 14 still failed.
  - [Boltz PR 527](https://github.com/jwohlwend/boltz/pull/527) remains unmerged
    MPS support. Its M3 test completed structure and affinity and reported only
    the known SVD fallback, but it did not publish a geometry audit.
    [Boltz issue 263](https://github.com/jwohlwend/boltz/issues/263) separately
    reports that an explicit bfloat16 experiment was about 20% slower on Mac
    MPS with only modest memory savings.
  - Apple documents that MPS kernels are tuned per GPU family; M1 is Apple GPU
    family 7, M2 family 8, and M3/M4 family 9. Thus identical PyTorch wheels can
    dispatch through different system-shipped kernels.

## Results

| Condition | n | Full wall time, mean ± SD | Model progress | pTM / pLDDT | Geometry |
|---|---:|---:|---:|---:|---|
| Build-8 FP32, no reset | 3 | 16.604 ± 0.706 s | 4 s each | 0.870176 / 0.907028 | 3/3 pass |
| Build-9 FP32, reset | 3 | 16.039 ± 0.127 s | 4 s each | 0.870176 / 0.907028 | 3/3 pass |

All six CIF files had the same SHA-256 and aligned Cα RMSD was numerical zero.
The affected M1 Pro build-8 run reported 13 seconds of model progress for this
same fold but invalid geometry. The exported two-engine run's 116.6-second wall
time includes IntelliFold startup/crash and is not a Boltz timing.

## Decision and rationale

There is no evidence that build 9 shortcuts Boltz or harms this M4 fold. The
apparent speed came from quoting the model-progress interval for a 71-residue,
one-seed, one-sample job with a local MSA, not end-to-end application latency.
The paired M4 control detects no output change and no performance penalty.

Retain the allocator reset for the M1 acceptance build because the upstream M1
Pro reproduction is unusually specific and reports the same exact remedy. Do
not claim the M1 is repaired until its post-update run passes. Do not generalize
the short-fold timing result to multi-input or resident campaigns; repeated
cache release could matter there and needs a separate throughput test.

## Reproduce

```bash
caffeinate -dimsu "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" \
  Validation/experiments/boltz_mps_allocator_v1/run.py \
  --input-yaml INPUT.yaml --msa QUERY.a3m \
  --control-wrapper BUILD8/pipeline/scripts/boltz_mps.py \
  --candidate-wrapper BUILD9/pipeline/scripts/boltz_mps.py
```

## Limits and what was not tested

- The affected M1 Pro remains the only decisive test of the proposed remedy.
- One 71-residue monomer, one seed/sample and one batch per process were tested.
- Longer complexes, ligands, multiple directory batches and resident iterative
  campaigns were not tested. The experiment establishes no general speedup.
- The local M4 probe not reproducing issue 193487 does not prove every M4/OS
  combination is immune.

## Next

Rerun build 9 on the updated M1 Pro. If it passes, add a multi-batch/resident M4
control before retaining per-batch cache release as a permanent default. If it
fails, gate Boltz on the affected stable runtime and validate a stable PyTorch
release containing the newer MPS allocator behavior.
