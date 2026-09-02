---
entry: 0061
title: Finish the M1 predictor-correctness repair
date: 2026-09-01
author: codex-gpt-5
type: bugfix
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1; external affected machine is an M1 Pro undergoing a macOS update
tags: [prediction, boltz, intellifold, mps, numerical-correctness, portability]
---

## Context

Unsigned beta build 8 was tested on the affected M1 Pro with the same
74-residue input, exported 5,179-record MSA, seed 42 and one diffusion sample
used in [[0060-fix-boltz-intellifold-apple-gpu-correctness]]. It falsified both
initial root-cause claims while proving that the new fail-loud geometry boundary
worked: Boltz FP32 still generated invalid coordinates and IntelliFold passed the
first replacement only to abort in a second MPS `GatherND` operation.

## What was done

- Preserved and read the complete build-8 logs from
  `prediction-20260901-201957`. Boltz reported success internally but Studio
  rejected 113 CA-CA or peptide C-N discontinuities. IntelliFold loaded the
  correct v2-flash weights, MSA and defaults, then aborted with an index width of
  540—the exact compacted atom count.
- Corrected Entry 0060: bfloat16 was a plausible portability risk, not the Boltz
  root cause. FP32 remains conservative, but no longer carries that claim.
- Replaced IntelliFold's two remaining advanced atom conversion paths. Boolean
  atom compaction/reversal and scatter-then-gather atom repetition now use
  order-preserving integer `index_select` mappings. Mask metadata is mapped on
  CPU; model tensors and inference remain on MPS, with CPU fallback disabled.
- Kept the earlier flattened token-pair lookup. The compatibility installer now
  validates and applies all three changes atomically under one process lock and
  remains idempotent.
- Added deterministic CPU equivalence checks for compaction, reversal, expanded
  sample batches and atom-count repetition.
- Added a Lightning callback to Boltz that synchronizes and releases only unused
  cached MPS allocations immediately before each prediction batch. This targets
  PyTorch issue 193487: an open, allocator-state-dependent silent FP32 matmul
  error reported across PyTorch 2.7.1–2.13.0. Studio is pinned to affected 2.13.0.
- Retained mandatory post-run geometry validation. The allocator reset is a
  targeted mitigation, not permission to trust an unchecked output.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| M1 Pro build-8 Boltz FP32 | 1 | rejected backbone discontinuities | 113 |
| M1 Pro build-8 IntelliFold v2-flash | 1 | result | second MPS GatherND abort, index width 540 |
| Atom compaction/reversal/repeat | 1 deterministic fixture | numerical equivalence to reference | exact |
| M4 Max repaired IntelliFold v2-flash | 1 | inference / geometry | 37.05 s / pass |
| M4 Max Boltz FP32 + allocator reset | 1 | inference / geometry | 4.5 s / pass |
| M4 Max Boltz FP32 + allocator reset | 1 | pTM / complex pLDDT | 0.870 / 0.907 |

The M4 timings cover the model prediction progress reported by each engine, not
full process startup. They are single-run correctness diagnostics, not throughput
benchmarks.

## Decision and rationale

Build 9 retains both predictors but makes their Apple-GPU boundaries explicit.
IntelliFold's failure is addressed at the exact unsupported tensor formulations.
Boltz's cross-Mac variance is consistent with a current, independently reported
PyTorch 2.13 MPS silent-numerics defect, so Studio resets the implicated allocator
state and still rejects any chemically discontinuous result.

PyTorch 2.14 was not silently substituted. It was not yet a stable release on
2026-09-01, and changing the core tensor runtime requires separate hash locking
and engine-specific numerical acceptance. A stable post-2.13 runtime remains the
preferred long-term replacement once released and validated.

## Reproduce

```bash
python3 -m unittest Tests/test_prediction_engine_safety.py

NANOHUNTER_ROOT="$HOME/.iproteinstudio" PYTORCH_ENABLE_MPS_FALLBACK=0 \
  caffeinate -dimsu "$HOME/.iproteinstudio/venvs/NanoHunter_intellifold/bin/python" \
  "$HOME/.iproteinstudio/scripts/intellifold_predict.py" INPUT.yaml \
  --out_dir OUTPUT --precision no --num_workers 0 --seed 42 \
  --num_diffusion_samples 1 --override --model v2-flash \
  --cache "$HOME/.iproteinstudio/models/intellifold"

NANOHUNTER_ROOT="$HOME/.iproteinstudio" PYTORCH_ENABLE_MPS_FALLBACK=0 \
  caffeinate -dimsu "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" \
  "$HOME/.iproteinstudio/scripts/boltz_mps.py" predict INPUT.yaml \
  --out_dir OUTPUT --cache "$HOME/.iproteinstudio/models/boltz2" \
  --accelerator gpu --devices 1 --num_workers 0 --override --seed 42
```

## Limits and what was not tested

- Build 9 has not yet been rerun on the affected M1 Pro because that machine is
  updating macOS. This is the decisive acceptance test. If Boltz still fails,
  the allocator reset is insufficient and Boltz must remain gated there until a
  stable post-2.13 PyTorch runtime passes numerical validation.
- The real repaired IntelliFold run covered v2-flash, one 74-residue monomer and
  one sample. Full v2 shares the three conversion functions but was not rerun.
- The Boltz reset was validated once on the M4 Max. A valid M4 output establishes
  no regression on this machine, not proof that it repairs every M1/OS pair.
- Multimers, ligands and multi-input batches were not repeated in this follow-up.

## Next

Install build 9 after the M1 Pro macOS update and repeat both engines on the same
cached input. Preserve the exported run. Mark this entry complete only if both
produce valid geometry; otherwise gate the failing engine by the observed
hardware/runtime combination and validate stable PyTorch 2.14 before changing
the managed dependency lock.
