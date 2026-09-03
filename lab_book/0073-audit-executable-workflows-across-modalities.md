---
entry: 0073
title: Audit executable workflows across modalities
date: 2026-09-02
author: gpt-5.6-sol
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [rfd3, mlx, ligand, partial-diffusion, motif-scaffolding, prediction, iterative, mcp, regression]
---

## Context

Entry [[0072-diagnose-small-molecule-rfd3-launch-copy]] identified why GUI run
`rfd3-20260902-220705` stopped before RFdiffusion3. The requested follow-up was
a token-efficient deep executable audit across Predict, iterative design,
protein RFdiffusion3 de-novo/partial/motif modes, small-molecule RFdiffusion3,
verification/results, MCP and the managed runtime.

## What was done

- Made the small-molecule runner preserve a GUI-owned `design.yaml` or
  `ligand.smi` already at its durable destination while retaining the external
  import behavior used by the standalone CLI.
- Ran the installed Javier BQ MLX implementation beyond preflight. This exposed
  a deeper defect: Foundry fixtures lived in one runtime-global `oracle/`
  directory and were keyed only by display name. A prior protein
  `untitled_design` fixture was silently reused for the fluorescein campaign.
- Moved fixture JSON, NPZ and manifests into each campaign's `rfd3/fixtures/`
  provenance directory. Added an explicit `milestone0_oracle.py --output-dir`
  boundary and applied the same rule to the legacy ligand helper.
- Exercised the real four-conformer GUI shape. This exposed another collision:
  all conformers at length 70 shared `rfd3/L70`, its done marker and queues.
  Repeated lengths now use their manifest bin index, while single/unique-length
  campaigns retain the old path for resume compatibility.
- Replaced independent rounded conformer shares with largest-remainder
  allocation, guaranteeing that conformer quotas sum to the user's requested
  design count even for small campaigns. Internal fixture names use stable
  numeric conformer suffixes, so duplicate or unsafe display labels cannot
  become path collisions.
- Rejected unsupported RFdiffusion precision values during preparation and
  corrected the bundled worked example from `float32` to the runner's `fp32`.
- Updated and staged the managed overlay provenance after testing. No weights or
  user results were changed.

## Results

The 20-step runs below are execution smokes, not product-performance
benchmarks. Previously measured default-schedule partial/motif evidence remains
in [[0067-add-live-rfd3-results-and-exact-motif-recovery]].

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Installed fluorescein MLX, one conformer, 20 steps | 1 | retained backbones | 1/1 |
| Same | 1 | ligand atoms retained | 31/31 |
| Same | 1 | adjacent binder Cα distances in 3.6–4.0 Å | 100% |
| Same → installed LASErMPNN | 1 | sequences emitted at requested length 70 | 1/1 |
| Installed fluorescein MLX, four conformers, 20 steps | 8 | exact weighted quota | 3/3/1/1; total 8/8 |
| Same | 4 | unique fixture and queue directories | 4/4 |
| Same | 8 | structures retaining 31 ligand atoms | 8/8 |
| Same | 8 | adjacent binder Cα distances in 3.6–4.0 Å | 100% each |
| Existing completed p53 motif campaign | 8 backbones / 16 sequences | holo / monomer / scored rows | 16 / 16 / 16 |
| Same results table | 16 | populated iPTM, ipSAE, binder, complex and motif metric cells | 16/16 per displayed metric |
| Existing same-day Predict, Protenix Mini | 1 | completed result rows | 1/1 |
| Existing same-day target preparation, Boltz | 1 | completed result rows | 1/1 |

Executable contract results:

- RFdiffusion3 workflow, partial/dual-RMSD, exact motif scoring, worked examples,
  predictor scheduling and live-results UI: pass.
- Iterative CLI, result UI and exact design cardinality: pass.
- Prediction engine safety and MSA retry/no-fallback policy: pass.
- Ligand conditioning and live RCSB generic-ligand acceptance: pass; the live
  set covered caffeine, aspirin, (S)-ibuprofen, beta-D-glucose and acetate.
- MCP bridge: 12/12 pass, including its capability-authenticated loopback test.
- Managed storage, storage policy, runtime transaction, installer lock,
  immutable component receipt, installer component/hardening, verified
  downloader, packaged resources, process cancellation, pipeline snapshot,
  workspace navigation and AI integration UI: pass.
- `swift build` completed with isolated compiler/module caches.

Some first attempts failed only because the restricted agent sandbox blocks
loopback sockets, process-table inspection, signals, managed-runtime writes or
the default compiler cache. Each was rerun at its real native boundary and
passed; those sandbox denials are not product failures. LASErMPNN initially
reported incomplete while Matplotlib built a first-use cache, then its exact
imports, `pip check`, inverse-folding smoke and repeated engine detection all
passed.

## Decision and rationale

Fixtures are campaign inputs, not a disposable global performance cache. Keeping
them with the run costs a short Foundry feature-preparation step per new
campaign, but prevents a valid-looking run from sampling the wrong target,
modality, length or ligand. Name-keyed global reuse was rejected because a
display name is not scientific provenance.

Conformer allocation is exact and deterministic. Independent rounding was
rejected because it can produce zero designs or a total different from the UI;
reusing length-only queue directories was rejected because conformer identity
must survive resume and flattening.

Existing default-schedule partial and motif GPU evidence was reused rather than
repeated. The audit spent new GPU work only at the previously unproven
small-molecule GUI boundary.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

~/.iproteinstudio/rfd3/.venv/bin/python Tests/test_workflow_pipelines.py
~/.iproteinstudio/rfd3/.venv/bin/python Tests/test_rfd3_partial_validation.py
~/.iproteinstudio/rfd3/.venv/bin/python Tests/test_rfd3_motif_scoring.py
~/.iproteinstudio/rfd3/.venv/bin/python Tests/test_rfd3_worked_examples.py
python3 Tests/test_rfd3_predictor_scheduling.py
bash Tests/test_rfd3_results_ui_contract.sh
bash Tests/test_iterative_cli_contract.sh
bash Tests/test_iterative_results_ui_contract.sh
python3 Tests/test_prediction_engine_safety.py
python3 Tests/test_prediction_msa_reliability.py
python3 Tests/test_mcp_bridge.py

CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swift-module-cache \
swift build --scratch-path /private/tmp/iproteinstudio-deep-audit-build
```

The installed ligand smoke used temporary campaign directories under
`/private/tmp/iproteinstudio-rfd3-gui-boundary` and
`/private/tmp/iproteinstudio-rfd3-multiconformer`; their complete commands and
stage logs remain there for this machine's immediate audit.

## Limits and what was not tested

- No new full 200-step small-molecule campaign was taken through Boltz affinity,
  apo prediction and final ranking. The new execution reached MLX backbones and
  real LASErMPNN; downstream prediction/scoring contracts and other completed
  campaigns were checked separately.
- No fresh end-to-end iterative campaign or fresh inference job for every
  installed predictor was launched. Current real Protenix Mini and Boltz outputs,
  engine detection and executable contracts were used to avoid redundant GPU
  work.
- Partial diffusion and motif scaffolding were not resampled in this audit;
  their one-backbone, 200-step installed MLX evidence is recorded in Entry 0067,
  and their current preparation/scoring/results contracts were rerun here.
- This is software/geometry validation, not experimental binding or catalytic
  validation. Hit-filter enrichment remains uncalibrated experimentally.
- No M1 acceptance or DMG build was performed.

## Next

Resume `rfd3-20260902-220705` from the app or start a new small campaign; its
installed runner now has all four repairs. For release acceptance, take one
packaged small-molecule campaign through affinity, apo and ranking on M1 and M4,
then retain that as the end-to-end fixture for future cross-modal audits.
