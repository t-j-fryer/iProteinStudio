---
entry: 0040
title: Add Protenix Constraint v0.5 as an honest experimental pocket engine
date: 2026-08-27
author: gpt-5.6-sol
type: port
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [protenix, constraints, iterative-design, mps, ui, install]
---

## Context

The isolated `iProteinHunter-beta/experiments/protenix_constraint_macos` study
established that the official Protenix constraint checkpoint strictly loads and
runs on native Apple MPS. Studio needed a deliberately narrow first integration:
protein-pocket conditioning in iterative design, not residue-pair or atom-pair
contacts, and not a misleading constraint toggle on Protenix v2.

The complete experimental lineage was subsequently re-audited directly against
the preserved beta receipt, failure log, 12 paired full-profile predictions,
analysis tables, figures and ChimeraX checksum manifest in
[[0043-protenix-constraint-macos-validation-lineage]]. That entry records the
Mac-enablement work and manuscript-grade evidence in full; the measurements
below remain the separate acceptance of the implementation actually shipped by
Studio.

## What was done

- Added the distinct product identity **Protenix Constraint v0.5 — Experimental**
  and runner identity `protenix-constraint-v0.5` only to iterative design.
- Ported upstream Protenix commit `4c355be4553512f72453ecbfb65e69f4c35d1413`,
  the validated 442-line MPS patch and official
  `protenix_base_constraint_v0.5.0` checkpoint into an isolated environment,
  source checkout and cache. The v2/Mini environment is not shared.
- Froze the checkpoint at 1,475,206,741 bytes and SHA-256
  `5358025b20b2212853ad75579be04387859557915f398a1d60f6a1a9a0c8c887`.
- Kept ESM disabled and absent. This released checkpoint has no trained
  `input_embedder.linear_esm.weight`; strict loading is retained and
  `fair-esm` in this profile is a hard failure.
- Added exact YAML-to-Protenix mapping from binder chain A and target residues
  B/C/... to one-based entity/copy/position pocket records. Invalid chains,
  binder residues, duplicates and out-of-range positions fail before compute.
- Fixed the runner so guided metadata is retained only for the constraint
  design phase and removed from every independent post-check.
- Fixed Protenix MSA generation to use the selected isolated profile while
  retaining Studio's exact-chain cache and fail-loud MSA policy.
- Added observed pocket geometry to `confidence.json` and
  `constraint_satisfaction.json`: mean/max nearest binder-to-epitope Cα
  distance and the fraction inside the recorded cutoff. The result browser
  labels these as geometry, not binding evidence.
- Added install detection and model removal. CPU mode, ligand campaigns and use
  as an independent post-predictor are rejected.

## Results

The installed Studio runtime was tested with the frozen 80-aa binder, 74-aa Bgx
target, exact target MSA, seed 73000, alternative pocket B18/B19/B21, 10
recycles, 200 diffusion steps and one sample.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Studio installed acceptance | 1 | model forward | 34.39 s |
| Studio installed acceptance | 1 | Protenix job after model load | 37.75 s |
| Studio installed acceptance | 1 | cold end-to-end adapter process | 116.97 s |
| Studio installed acceptance | 1 | maximum resident set size | 4.06 GiB |
| Studio installed acceptance | 1 | iPTM | 0.7765 |
| Studio installed acceptance | 1 | ipSAE(min) | 0.1532 |
| Studio installed acceptance | 1 | alternative-pocket mean nearest Cα distance | 25.01 Å |
| Studio installed acceptance | 1 | requested residues within 8 Å | 0/3 |

The earlier beta paired full profile (three seeds per arm, same M4 Max) measured
51.01 s mean wall time and 24.74 Å mean alternative-pocket distance for the
alternative-pocket arm. The new 25.01 Å result therefore reproduces the earlier
behavior; it does **not** demonstrate strong steering.

The log proved native MPS, FP32/native Torch kernels, strict load with no
incompatible keys, 368.30M parameters, 1,183 MSA rows, exactly three loaded
pocket residues at 8 Å and exactly one CIF/summary/full-confidence output.

## Decision and rationale

Keep the engine available, separate and conspicuously experimental because the
user explicitly wants to explore pocket-conditioned iterative design and the
technical runtime is reproducible. Do not market pocket conditioning as reliable
epitope forcing: the prior three-seed test found practically negligible and
inconsistent shifts, and the installed acceptance again left the alternative
epitope about 25 Å away.

Keep 8 Å as the default because it is the upstream
`examples/example_constraint_msa.json` value and the only setting tested here.
This value is a learned **token-centre** (protein Cα) pocket feature, not an
8 Å nearest-heavy-atom contact. Boltz remains a different mechanism with
Studio's 6 Å explicit pocket/contact setting; the numbers are not interchangeable.

Residue-pair contacts remain out of this product surface. The beta study found
that they forced geometry much more strongly but caused a large iPTM penalty;
they require their own controlled product decision rather than being smuggled
in as an advanced pocket option.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

caffeinate -dimsu swift build
caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python Tests/test_workflow_pipelines.py

NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
  bash /Users/thomasfryer/.iproteinstudio/setup_pipeline.sh --detect

caffeinate -dimsu /usr/bin/time -l \
  /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix_constraint/bin/python \
  /Users/thomasfryer/.iproteinstudio/scripts/protenix_predict.py \
  --yaml /private/tmp/iproteinstudio-protenix-constraint-acceptance.yaml \
  --output /private/tmp/iproteinstudio-protenix-constraint-acceptance-output \
  --nanohunter-root /Users/thomasfryer/.iproteinstudio \
  --model constraint --seeds 73000 --samples 1
```

## Limits and what was not tested

- The installed acceptance is one seed and one protein-protein complex. It
  proves the port and reproduces the weak alternative-pocket response; it does
  not establish general scientific utility.
- No 6/7/8/10 Å Protenix dose-response was run. The UI therefore does not imply
  that a tighter number would work better.
- No complete multi-cycle MPNN campaign was spent for this port. Its actual
  predictor handoff, output and inverse-folding structure contract are shared
  with the already tested Protenix iterative path, while engine-specific
  template/CLI contracts were executed directly.
- Nanobody and multimer pocket inputs passed mapping contracts but did not get
  new GPU campaigns.
- Residue-pair and atom-pair Protenix constraints are intentionally absent.

## Next

Run a matched, target-diverse test of unconstrained versus pocket-conditioned
cycle-00 proposals and measure unique interface clusters that survive sequence
design plus unconstrained post-prediction. Only persistence after removing the
prior would justify promoting this engine beyond Experimental.
