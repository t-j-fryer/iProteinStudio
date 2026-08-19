---
entry: 0024
title: Make numbers editable, default to Richardson cartoons, and exercise every installed method
date: 2026-08-18
author: codex-gpt-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, py2dmol, predictors, rfd3, gpu, msa]
---

## Context

The macOS `Stepper` labels used throughout Studio displayed a number but only the
arrow buttons could change it. The structure viewer also opened in Tube / Spectrum
even though Cartoon / Richardson is the more useful starting point for proteins.
The resulting UI changes needed another real-app pass, and every installed science
method needed an acceptance launch with its actual device recorded rather than
assuming that successful execution meant GPU execution. This follows
[[0023-fit-viewer-controls-and-audit-minimum-layout]].

## What was done

- Added `EditableIntStepper` in `Views/RunUXComponents.swift`: a synchronized text
  field and arrow stepper that commits on Return or focus loss, clamps valid
  out-of-range integers, and restores the current value after invalid text.
- Replaced all 16 arrow-only numeric selectors in iterative design, Predict, and
  RFdiffusion3. There are no direct SwiftUI `Stepper` uses left outside the shared
  component. The binder minimum is additionally constrained by the current maximum.
- Changed py2Dmol's initial state in `Resources/web/py2dmol/viewer.html` to Cartoon
  with the Richardson preset. Both the renderer state and visible controls now start
  with those values.
- Rebuilt and inspected the release app. Accessibility automation typed valid,
  invalid, and out-of-range values into a binder-length field and verified the
  synchronized arrow control. Predict and RFdiffusion3 advanced forms exposed their
  numeric values as editable text fields, and RFdiffusion3 retained its fixed
  navigation plus scrollable content at the 1080 × 720 minimum window.
- Ran real acceptance inputs through every installed predictor, both IntelliFold
  model sizes and every installed sequence designer. All long-running commands used
  `caffeinate -dimsu`.
- The method matrix found a reproducible OpenFold-3 failure: its public query schema
  accepts arbitrary alignment paths, but its raw-MSA parser filters by known source
  basenames. A valid shared-cache file such as `target_full_msa.a3m` was silently
  discarded. `openfold_predict_one.py` now keeps the cache immutable and copies each
  raw A3M/STO into a private per-chain adapter directory as `colabfold_main.*`.
  Missing files, unsupported suffixes, and ambiguous multiple main alignments fail
  loudly. A contract test covers the arbitrary-cache-name case.
- Updated the RFdiffusion3 overlay checksum/version and staged the corrected adapter
  into the managed runtime used for the acceptance retry.
- Updated `IterativeCommandContractHarness.swift` for the shared target-MSA cache
  environment added to the real command builder.

## Results

All values below are acceptance results from the machine in the header. Durations
are recorded as observed wall time, not presented as comparative benchmarks.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| aCbx, Boltz + IntelliFold PyTorch flash + IntelliFold JAX flash + AF3 + OpenFold-3 | 5 engines | completed outputs | 5/5 |
| aCbx, IntelliFold PyTorch full v2 + IntelliFold JAX full v2 | 2 engines | completed outputs | 2/2 |
| Boltz steering-potentials route | 1 job | completed outputs | 1/1 |
| Boltz protein–fluorescein affinity-head route | 1 job | completed outputs | 1/1 |
| RFdiffusion3 MLX, 65-residue backbone, 20 diffusion steps | 1 job | generated backbones | 1/1 |
| SolubleMPNN, ProteinMPNN, LigandMPNN, LASErMPNN, AbMPNN, AntiFold | 6 designers | completed outputs | 6/6 |
| Flash five-engine prediction retry after the OpenFold fix | 1 batch | wall time | 61.3 s |
| Full-v2 two-engine prediction batch | 1 batch | wall time | 450.3 s |
| Native WebKit viewer state | 1 load | Cartoon + Richardson selected | 1/1 |
| Responsive viewer harness | 4 viewport sizes | controls fit without overlap | 4/4 |

Device evidence was checked separately from completion:

- Boltz, IntelliFold PyTorch, IntelliFold JAX/MPS, AlphaFold 3, OpenFold-3 MLX,
  RFdiffusion3 MLX, and AntiFold explicitly selected an Apple GPU/MPS device.
  An unsandboxed IntelliFold PyTorch device probe reported `accelerate_device=mps`,
  `mps_built=True`, and `mps_available=True`. A first sandboxed probe reported CPU
  because Metal was unavailable inside the filesystem sandbox; that result was
  rejected rather than misclassifying the production environment.
- ProteinMPNN, SolubleMPNN, LigandMPNN, and AbMPNN use the upstream
  CUDA-otherwise-CPU device branch and therefore ran on CPU on this Mac.
- LASErMPNN is CPU-only in the integrated upstream route.

The device classification is intentionally explicit: every named method completed,
but not every upstream method is capable of using Apple's GPU.

## Decision and rationale

Use one shared number-entry component rather than modifying every form differently.
This preserves arrow-key/stepper convenience, supports direct entry for large design
counts, and centralizes range handling and accessibility.

Use Cartoon / Richardson as an initial viewer state, not a forced state. It gives a
clear secondary-structure overview while preserving all py2Dmol controls for users
who need surfaces, sticks, alternative colour presets, or rendering effects.

Adapt OpenFold's filename convention at the narrow engine boundary rather than
renaming or duplicating the global cache. The shared cache remains exact and
immutable for every workflow, while OpenFold receives the convention it actually
parses. Generating a new MSA or silently folding without one was rejected because it
would violate the reproducibility and fail-loud contracts.

## Reproduce

The acceptance artifacts and adapter command manifests were retained under
`/private/tmp/iproteinstudio-gpu-*-20260818`. In particular:

```bash
cd /Users/thomasfryer/iProteinStudio

sed -n '1,160p' /private/tmp/iproteinstudio-gpu-flash-20260818/run_summary.json
sed -n '1,160p' /private/tmp/iproteinstudio-gpu-full-20260818/run_summary.json
sed -n '1,160p' /private/tmp/iproteinstudio-gpu-rfd3-20260818/rfd3/run_manifest.json

/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_intellifold/bin/python \
  -c 'from accelerate import Accelerator; import torch; a=Accelerator(); print(a.device); print(torch.backends.mps.is_built()); print(torch.backends.mps.is_available())'

caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_workflow_pipelines.py
caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
caffeinate -dimsu /private/tmp/iproteinstudio-workflow-contract
caffeinate -dimsu /private/tmp/iproteinstudio-iterative-contract

git diff --check
bash -n Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh \
  Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh
caffeinate -dimsu swift build
caffeinate -dimsu ./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
```

`Tests/test_workflow_pipelines.py` must use the managed RFdiffusion3 Python because
the system Python does not include PyYAML.

## Limits and what was not tested

- This was one small acceptance input per method or feature route, not a statistical
  quality benchmark and not the combinatorial product of every model, target type,
  option, length, and scheduler setting.
- The RFdiffusion3 job used a cached Foundry fixture and exercised the MLX backbone
  route; it did not repeat an entire sequence-design and multi-predictor campaign.
- Device probes must run outside a restrictive sandbox; otherwise macOS can hide
  Metal and make an MPS-capable environment appear CPU-only.
- LASErMPNN and the LigandMPNN family completing on CPU does not establish any GPU
  implementation for those upstream tools.
- Accessibility automation covered representative editable numbers and form
  exposure, not a complete VoiceOver, keyboard-focus, large-text, or contrast audit.
- Acceptance artifacts live in `/private/tmp` and may be removed by macOS.

## Next

Continue the full VoiceOver and keyboard-navigation pass tracked in the project
status. Preserve unsandboxed device probes in future GPU acceptance work so a
restricted diagnostic cannot be mistaken for the production device selection.
