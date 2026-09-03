---
entry: 0076
title: Enforce RFdiffusion3 EMA weight provenance
date: 2026-09-03
author: gpt-5.6-sol
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [rfd3, mlx, weights, installer, mcp, provenance]
---

## Context

The MLX port's pinned source already contained an upstream repair for selecting
Foundry's EMA inference network, but Studio's vendored overlay replaced its
exporter with an older implementation. That implementation searched wrapper
attributes in an order that encountered `EMA.model` before `EMA.shadow`. The
installed artifact honestly reported `which: model (raw)`, yet its raw SHA-256
was pinned by both installation scripts and accepted by app/MCP detection.

## What was done

- Added one shared `rfd3_weight_set.py` selector that identifies the EMA wrapper
  structurally, defaults explicitly to `shadow`, and refuses fallback to raw.
- Changed the exporter to verify every non-scalar tensor against the requested
  checkpoint namespace before writing anything, and to embed deterministic
  `weight_set`, `which`, and checkpoint-filename metadata.
- Made the installer validate both the new deterministic SHA-256 and embedded
  EMA metadata. Future installs regenerate any legacy/raw artifact.
- Made `setup_pipeline.sh --detect` read only the small safetensors header and
  report unverified weights as `update`. This path is shared by the app Engines
  screen and MCP `system_detect`.
- Added the same fail-closed metadata gate to the MLX backbone runner and writes
  the weight provenance into every run manifest.
- Added a native Swift header check so the RFdiffusion3 GUI is disabled before
  launch when the artifact is raw or unlabelled.
- Synchronized the selector through both bundle staging paths, repaired the
  active managed runtime, and rewrote its installation receipt.
- Assembled the release app and verified its nested code signature and packaged
  installer/runtime gates.

No checkpoint or weight file was added to Git.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Corrected export | 807 tensors | checkpoint namespace | 800 shadow-only, 7 identical, 0 raw-only, 0 neither |
| Corrected artifact | 1 | SHA-256 | `736e6f5e11ec70dea58903deb2290031e366d2b0b2478e63208a2541650a04d6` |
| Legacy artifact | 1 | fail-closed provenance gate | rejected |
| Default-schedule MLX smoke, 55-aa binder, 200 steps, 2 recycles | 1 | accepted backbone / wall time | 1/1 / 30.35 s |
| Default-schedule smoke | 54 peptide intervals | mean C-alpha spacing | 3.830 A |
| Python weight-provenance suite | 4 | tests passed | 4/4 |
| Installer hardening contract | 1 | result | pass |
| Workflow pipeline contract | 1 | result | pass |
| Swift debug build | 1 | result | pass |
| Packaged release app | 1 | deep signature and EMA resources | pass |
| Installed app/MCP detection | 1 | RFD3 state | `ok`, verified EMA weights |

The 200-step smoke manifest records `weight_set: shadow` and
`weight_provenance: shadow (EMA)`. It is an execution/provenance test, not a
binder-quality validation: the old no-hotspot mNeonGreen feature fixture still
produced a minimum inter-chain distance of 2.39 A and a binder radius of
gyration of 20.79 A. Those observations are consistent with the separate
target-COM origin problem and must not be interpreted as a successful binder.

## Decision and rationale

EMA provenance is enforced at four boundaries: export, install, discovery and
inference. Hash-only validation was rejected because a stale raw hash can be
mistakenly blessed, as happened here. Metadata-only validation was also rejected
for installation because metadata does not prove tensor bytes; the installer
therefore requires both.

Raw weights remain an explicit developer A/B option through
`RFD3_WEIGHT_SET=model`, but such an artifact cannot be promoted into the
Studio runtime. The deployable default is always Foundry's EMA `shadow`, matching
the network its eval-mode wrapper actually executes.

For de-novo protein binders with no user hotspot, target-COM placement was not
relabelled as whole-surface sampling. A globular protein's COM is generally
buried, so that behavior is scientifically different. A future unbiased mode
should generate reproducible solvent-exposed surface patches and stratify
hotspot-conditioned jobs across them.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

PYTHONPYCACHEPREFIX=/private/tmp/iproteinstudio-pycache \
  python3 -m unittest Tests.test_rfd3_weight_provenance
bash Tests/test_installer_hardening_contract.sh
~/.iproteinstudio/rfd3/.venv/bin/python Tests/test_workflow_pipelines.py

bash ~/.iproteinstudio/rfd3/install_rfd3.sh --check
python3 ~/.iproteinstudio/mcp/studioctl.py detect

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-swift15-cache-20260903 \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iproteinstudio-swift15-cache-20260903 \
swift build

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-swift15-cache-20260903 \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iproteinstudio-swift15-cache-20260903 \
./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
```

The explicit 15.4 SDK was required because the just-updated Command Line Tools
6.3.3 installation currently points its default symlink at an SDK whose Swift
interfaces report 6.3.2; that host mismatch is independent of this code change.

## Limits and what was not tested

- No clean-machine or DMG install was performed. The exact shipped setup and
  staging contracts were exercised, and the existing managed installation was
  repaired in place.
- Partial diffusion and motif scaffolding were not rerun with the corrected
  weights in this entry. Their shared MLX runner now enforces the same artifact,
  but scientific regression runs remain required.
- The smoke used one previous mNeonGreen fixture and one seed. No interface
  prediction, binder-alone prediction, fold confidence or experimental truth
  was evaluated.
- No automatic whole-surface origin sampler was implemented here.

## Next

Implement and benchmark a deterministic surface-patch scan for no-hotspot
protein binder jobs, exposing patch coverage and patch identity in each design's
provenance. Then rerun the partial-diffusion and motif examples with EMA weights
before the next distributable DMG.
