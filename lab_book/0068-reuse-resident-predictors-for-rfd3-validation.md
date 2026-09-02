---
entry: 0068
title: Reuse resident predictors for RFdiffusion3 validation
date: 2026-09-02
author: gpt-5-codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [rfd3, predictors, resident, protenix, mps, performance]
---

## Context

Entries [[0046-implement-campaign-resident-predictors]] and
[[0053-make-resident-scheduling-automatic]] established measured scheduling for
iterative design: keep Boltz 2, IntelliFold v2 Flash/full and Protenix Mini
resident, but use cycle waves for full Protenix v2. Entry
[[0066-add-rfd3-partial-motif-and-dual-validation]] added independent
complex and binder-alone re-prediction to RFdiffusion3 campaigns. Those two
stages still launched one fresh process per design, repeating model loads and
failing to reuse the already validated scheduling work.

## What was done

- Made the shared RFdiffusion3 `run_predictors.py` runner choose the measured
  engine policy automatically. Boltz, both IntelliFold models and Protenix Mini
  use one native-MPS resident worker per prediction stage. Full Protenix v2 uses
  one directory wave. OpenFold remains per-input because the existing resident
  worker has no validated OpenFold session.
- Reused the existing immutable, checksummed file-queue protocol. Every request
  and readiness receipt must report one model load, MPS, and no CPU fallback.
- Submitted one design per resident request. This retains a single loaded model
  while allowing `prediction_metrics.csv` to checkpoint after every structure,
  preserving live RFdiffusion3 results and restart granularity.
- Preserved the explicit MSA contract. A stage with missing `msa` fields or a
  mixture of real-MSA and single-sequence jobs fails before its worker starts.
- Kept complex and binder-alone sessions separate. The score/select boundary
  between them is resumable and may be long; retaining a GPU owner across that
  boundary would create an orphan-prone daemon and hold unified memory while no
  prediction work is available.
- Recorded `scheduler`, resident session, startup, request wall time, wave size,
  and `model_load_count` in the prediction CSV/manifest.
- Added an end-to-end fake-worker contract proving two IntelliFold designs use
  one resident session and two Protenix v2 designs use one directory load.

## Results

The real smoke used two existing 70-residue designs copied to an isolated
`/private/tmp` directory. The binder-only inputs used explicit empty MSAs. The
complex inputs paired the same 70-residue binders with one 85-residue target and
its existing exact cached MSA. Protenix Mini used its shipped default of five
samples. These are smoke timings, not a replacement throughput benchmark.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Binder-only Protenix Mini stage | 2 designs | resident model loads | 1 |
| Same | 2 requests | request wall times | 5.72 s, 1.24 s |
| Same | 1 session | startup time | 11.82 s |
| Complex Protenix Mini stage | 2 designs | resident model loads | 1 |
| Same | 2 requests | request wall times | 6.65 s, 2.33 s |
| Same | 1 session | startup time | 10.02 s |
| Both stages | 4 designs | successful prediction rows | 4/4 |
| Both stages | 2 sessions | native MPS / CPU fallback | 2/2 / 0 |
| Synthetic resident contract | 2 designs | worker sessions / receipts | 1 / 2 |
| Synthetic Protenix v2 contract | 2 designs | directory model loads | 1 |

The real resident worker's geometry validation completed before each success
receipt. Each Protenix job retained all five requested samples; the campaign
metrics deliberately select the normalized ranked structure, as before.

## Decision and rationale

RFdiffusion3 verification now shares the same engine-specific policy as
iterative design rather than maintaining a slower scheduling fork. Residency is
scoped to one stage, which removes repeated per-design loads while preserving
stage-level resume and releasing GPU memory before scoring or input preparation.

Full Protenix v2 remains the deliberate exception. Entry 0046 measured its
resident campaign slower than its cycle-wave campaign, so using residency merely
for uniformity would contradict the evidence. OpenFold is also not described as
resident: batching it may be worthwhile, but that change needs its own output-
normalization and Apple-GPU acceptance rather than an untested label.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
  bash Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh --detect
python3 Tests/test_rfd3_predictor_scheduling.py
python3 Tests/test_prediction_engine_safety.py
/Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_workflow_pipelines.py
bash Tests/test_rfd3_results_ui_contract.sh
swift build --scratch-path /private/tmp/iproteinstudio-rfd3-resident-build
```

The isolated real-smoke artifacts from this entry are at
`/private/tmp/iproteinstudio-rfd3-resident-1EYWD3`; they are disposable and are
not part of the repository or release bundle.

## Limits and what was not tested

- Real inference in this entry exercised Protenix Mini only, with two monomers
  and two single-target complexes on one M4 Max.
- Boltz and IntelliFold use the previously validated resident implementation
  and gained new synthetic orchestration coverage, but were not re-folded here.
- Full Protenix v2's new RFdiffusion directory route has functional fake-adapter
  coverage; its measured scheduling decision comes from entry 0046 rather than
  a new full-model run.
- OpenFold remains per-input. No M1 run or packaged DMG was produced.
- The timings above cannot support a general speedup claim across lengths,
  target sizes, engines, or Apple GPU generations.

## Next

Exercise one multi-design Boltz and IntelliFold RFdiffusion verification stage
on the updated M1 and M4 release candidates. Add a resident OpenFold session only
after a governed directory/resident comparison proves the lifecycle and output
normalization are correct.
