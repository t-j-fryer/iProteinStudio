---
entry: 0003
title: Compare Boltz bfloat16 and Studio FP32 on M4
date: 2026-09-01
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
---

## Question

Does Studio's current FP32 MPS execution boundary alter speed or output relative
to Boltz 2.2.1's upstream `bf16-mixed` default on the same short M4 fold?

## Design

Three fresh processes per arm, interleaved A-B-B-A-A-B, using the same governed
runner and exact input as Validation Entry 0002. The control wrapper is the
retained build-8 wrapper with only Trainer precision and its diagnostic marker
changed to `bf16-mixed`; its SHA-256 is recorded before compute. The candidate is
the packaged build-9 wrapper. Entry 0002 already shows that the candidate's
allocator reset alone is output-identical to FP32 without the reset.

## Results

The planned six-run contrast stopped after the first control because it revealed
that the contrast did not exist. Lightning printed both:

```text
Using bfloat16 Automatic Mixed Precision (AMP)
CUDA is not available ... Disabling autocast.
```

The completed model interval was 4 seconds. Its CIF independently passed the
shipped geometry validator and had SHA-256 `f3a132c572d3…`, exactly matching all
six FP32 outputs in Entry 0002. pTM (`0.8701755404472351`) and complex pLDDT
(`0.907027542591095`) were also exact matches.

The temporary control wrapper then exited 1 because its copied location did not
contain the relative geometry-validator script. This was a harness-path failure
after successful inference, not a predictor failure; the raw partial output was
preserved. An earlier attempt failed before inference because placing the wrapper
directly in `/private/tmp` exposed an unrelated `matplotlib` namespace directory;
that raw log was also preserved. Neither failure was counted as a model run.

## Decision

Do not describe Boltz 2.2.1's current Mac path as real bfloat16 inference.
PyTorch-Lightning 2.5 disables its CUDA-oriented autocast plugin on MPS, so the
old labelled path and Studio's explicit FP32 path execute the same precision on
this runtime. Explicit `precision=32` is retained because it states the actual
contract and cannot begin silently using an unvalidated MPS autocast path after
a dependency update.

No further GPU replicates were spent on a nonexistent precision contrast.

## Inputs and reproduction

See `Validation/experiments/boltz_mps_precision_v1/README.md` and the generated
ignored `Validation/output/boltz_mps_precision_v1/manifest.json`.

## Limits

One short monomer and one seed/sample. A future Lightning/PyTorch combination
may implement MPS bfloat16 autocast; that would be a new scientific runtime and
would require a fresh paired experiment rather than inheriting this result.
