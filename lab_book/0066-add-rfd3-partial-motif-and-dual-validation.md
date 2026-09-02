---
entry: 0066
title: Add RFdiffusion3 partial diffusion, motif scaffolding and dual validation
date: 2026-09-02
author: gpt-5-codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [rfd3, mlx, partial-diffusion, motif-scaffolding, validation, ui]
---

## Context

> **Later boundary:** Entry
> [[0067-add-live-rfd3-results-and-exact-motif-recovery]] supersedes this
> entry's explicit side-chain-atom adapter evidence and adds a default-schedule,
> three-residue validation. The three-mode architecture and dual-validation
> decisions recorded here remain current.

Studio exposed RFdiffusion3 only as de-novo binder generation. Current Foundry
supports partial diffusion and unindexed motif scaffolding, but these paths have
had important version-dependent failures: tagged v0.1.9 did not propagate
`partial_t` correctly, older partial diffusion centred a small diffused binder
using the whole complex, and the PyTorch path has previously failed for
`unindex` with internal batch size above one. Production outputs can also retain
virtual atoms or contain invalid joins. The relevant upstream records are
[Foundry input documentation](https://github.com/RosettaCommons/foundry/blob/production/models/rfd3/docs/input.md),
[partial diffusion issue 290](https://github.com/RosettaCommons/foundry/issues/290),
and [unindex batching issue 109](https://github.com/RosettaCommons/foundry/issues/109).

Finished binder-design validation also conflated two different questions:
whether chain A recovered its own fold and whether it remained in the designed
pose after aligning the fixed target. Iterative campaigns only optionally
re-folded complexes and did not retain an auditable multi-metric hit verdict.

## What was done

- Added explicit **De novo**, **Partial diffusion**, and **Motif scaffolding**
  modes to the RFdiffusion3 form and request schema.
- Normalized an input binder/motif chain to A and fixed target chains to B, C,
  D… for every existing-complex workflow.
- Ported Foundry's `partial_t` schedule semantics into the pinned Javier BQ MLX
  sampler. `partial_t` is treated as coordinate-noise standard deviation in Å,
  with the production EDM schedule truncated at that value.
- Kept Foundry's current diffused-region centre-of-mass behavior by preventing
  de-novo `infer_ori_strategy` and `ori_token` controls from leaking into a
  partial or motif request.
- Added explicit unindexed motif residues and atom selections. The output layer
  records `diffused_index_map`, fixes the mapped residues during MPNN, removes
  guidepost/virtual atoms, and rejects invalid Cα/peptide geometry before a
  sample can count toward the requested quota.
- Added bounded resampling with `rejected_samples.csv`; failure to fill the
  exact requested backbone count remains fatal. Resume reconstructs both
  accepted and rejected sample seeds before allocating the next batch.
- Added complex and binder-alone re-fold stages to protein RFdiffusion3
  campaigns and optional binder-alone re-folding to iterative post-checks.
- Added saved, independently adjustable iPTM, ipSAE(min), target-aligned binder
  RMSD, binder pLDDT and binder-alone RMSD filters. A missing requested metric
  fails its gate instead of being ignored.
- Split structural self-consistency into:
  1. target-aligned binder-pose RMSD, which detects movement to the wrong target
     surface;
  2. binder-fit backbone RMSD, which measures fold recovery independently of
     pose; and
  3. binder-alone versus complex RMSD, which measures preorganisation.
- Preserved per-predictor values and filter provenance in CSV/JSON output and
  exposed pass/fail status and failed filters in the persistent results browser.
- Runs iterative structural scoring with the selected predictor's managed
  Python rather than assuming an undeclared NumPy installation in macOS Python.
- Added `Tests/test_rfd3_partial_validation.py` to prove partial requests do not
  inherit de-novo origin controls and that target-aligned RMSD catches a rigidly
  displaced binder even when binder-fit RMSD is zero.

## Results

These were bounded smoke/regression tests, not production throughput benchmarks.
The deliberately short 20-step, one-recycle setting exists only to exercise the
real MLX/Metal execution and output contracts.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Partial diffusion, `partial_t=0.1 Å`, 20 steps, batch 1 | 1 | input-to-output binder Cα RMSD | 0.040 Å |
| Motif scaffolding, 20 steps, requested batch 2 | 2 retained | valid independent geometry checks | 2/2 |
| Same motif run | 4 attempted | malformed samples rejected and resampled | 2 |
| Same motif run | 2 retained | mapped motif insertion RMSD | 0.813 Å; 0.786 Å |
| Simulated mid-batch resume after seed 403 | 1 remaining | next sample seed | 404 |
| Synthetic rigid-body scoring regression | 1 pair | displaced pose detected while binder-fit RMSD remained <1e-6 Å | pass |

The observed motif attempt durations (1.02–1.30 s/attempt) are smoke-test
measurements on a truncated schedule and must not be presented as product
performance.

## Decision and rationale

Studio now exposes the three RFdiffusion3 concepts as separate workflows rather
than an advanced parameter on de-novo generation. Their input semantics differ
enough that one form path would allow stale length, origin or coordinate-fixing
state to cross modes silently.

The MLX sampler remains the Apple-GPU execution path. We ported the current
Foundry schedule behavior rather than switching the app to the tagged PyTorch
release, because the tagged release is known to contain the broken partial
implementation and this project already validates and distributes the MLX path.
The output geometry gate is mandatory because upstream cleanup settings alone
do not prove a usable backbone.

Target-aligned binder RMSD is the RMSD hit gate. Binder-fit backbone RMSD remains
visible as a diagnostic, because using it as the interface gate would accept a
correct binder fold translated or rotated onto the wrong epitope.

The starting filter values are editable and saved as provenance, not claimed as
universal biological truth. They are guided by established self-consistency
filters in the original [RFdiffusion paper](https://www.nature.com/articles/s41586-023-06415-8)
and the public [BindCraft implementation](https://github.com/martinpacesa/BindCraft),
but experimental success must calibrate them for each campaign class.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
python3 Tests/test_rfd3_partial_validation.py
bash Tests/test_iterative_cli_contract.sh
/private/tmp/iproteinstudio-rfd3-feature.PTr3EB/.venv/bin/python Tests/test_workflow_pipelines.py
bash Tests/test_iterative_results_ui_contract.sh
bash Tests/test_packaged_resource_bundle.sh
bash Tests/test_installer_component_contract.sh
bash Tests/test_pipeline_snapshot.sh
python3 Tests/test_design_cardinality.py
python3 Tests/test_prediction_engine_safety.py
swift build --scratch-path /private/tmp/iproteinstudio-swift-build-rfd3

caffeinate -dimsu \
  /private/tmp/iproteinstudio-rfd3-feature.PTr3EB/.venv/bin/python \
  /private/tmp/iproteinstudio-rfd3-feature.PTr3EB/scripts/generate_backbones.py \
  --fixture /private/tmp/iproteinstudio-rfd3-feature.PTr3EB/oracle/oracle_motif_smoke.npz \
  --output /private/tmp/iproteinstudio-rfd3-feature.PTr3EB/motif_batch2 \
  --num-designs 2 --steps 20 --recycle 1 --batch-size 2 \
  --seed-start 401 --precision bf16 --motif-residues A50 --cache-limit-gb 4
```

## Limits and what was not tested

- No complete 200-step, multi-backbone partial or motif campaign was run through
  inverse folding and every selectable verification engine in this pass.
- The GPU smoke fixtures contained one binder chain, one target chain and one
  motif residue. Multi-target and multi-residue mapping are covered by explicit
  data contracts but still need a larger empirical campaign.
- Motif functional success, target binding and filter enrichment were not tested
  experimentally. Geometry and model confidence are not substitutes for them.
- The batch-2 result establishes compatibility only for this MLX fixture. It
  does not claim the historical PyTorch/Foundry batching issue is universally
  resolved upstream.
- No release DMG was built in this entry; the source and Swift package build
  were validated before merge.

## Next

Run a governed validation campaign spanning several `partial_t` values and
multi-residue motifs, then compare retained contact geometry, target-aligned
binder pose, binder-only preorganisation and experimental hit enrichment. Use
those data to replace generic starting filters with workflow-specific presets.
