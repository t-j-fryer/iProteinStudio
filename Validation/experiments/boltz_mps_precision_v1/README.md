# Boltz MPS precision control

This paired experiment reuses
`../boltz_mps_allocator_v1/run.py` with two fingerprinted wrappers:

- control: build-8 wrapper changed only from FP32 to Boltz's upstream
  `bf16-mixed` setting;
- candidate: build-9 FP32 plus its allocator reset.

Three fresh processes per arm use the exact same YAML, MSA, checkpoint, seed,
sample count and model defaults in an interleaved A-B-B-A-A-B schedule. This
tests the complete current runtime boundary against the previous upstream
precision behavior; Entry 0002 separately isolates the allocator reset itself.

The planned sweep stopped after its first scientific control: Lightning 2.5
reported that CUDA was unavailable and disabled autocast, so Boltz's
`bf16-mixed` label was actually executing FP32 on MPS. That output was
bit-identical to Entry 0002. Further replicates could not compare precisions
because no precision contrast existed; see Validation Lab Book 0003.
