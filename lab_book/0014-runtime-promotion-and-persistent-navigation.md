---
entry: 0014
title: Promote the standalone runtime and keep workflow navigation available
date: 2026-08-13
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, install, reproducibility, rfd3, navigation]
---

## Context

Entry [[0013-standalone-intellifold-and-scaffold-msas]] validated a complete
installation under `~/.iproteinstudio_freshtest`, while the Finder-launched app
correctly continued to use its production root, `~/.iproteinstudio`. That older
root had AlphaFold 3 but incomplete Boltz, IntelliFold and OpenFold model data,
so the Engines sheet appeared to contradict the successful fresh-install test.

The workflow segmented control also disappeared whenever any controller reported
an active run. A detached RFdiffusion3 campaign can run for days, so this trapped
the user in its progress screen for the lifetime of the campaign.

## What was done

- Made the Iterative design / RFdiffusion3 / Predict selector permanently
  visible. An active-workflow banner explains that inspection is allowed.
- Disabled each workflow's Start button while either of the other two workflows
  is active. This retains the original protection against overlapping GPU-heavy
  jobs without removing navigation.
- Added a stable accessibility identifier to the workflow selector and banner.
- Added the exact managed-runtime path and a Refresh status button to the Engines
  sheet, and explained that models live outside both the app and source repo.
- Extended environment relocation to RFdiffusion3's separate `rfd3/.venv`.
  Relocation now rewrites console scripts, activation files, editable import
  hooks and nested `direct_url.json` metadata for both venv layouts.
- Promoted the validated standalone root to `~/.iproteinstudio`. The preceding
  partial runtime was preserved as
  `~/.iproteinstudio_before_standalone_20260813`; its AF3 parameters, projects,
  alignments, target predictions, examples and thumbnails were copied into the
  promoted root before the swap.
- Continued all source work exclusively in the clean GitHub clone at
  `/Users/thomasfryer/iProteinStudio`.

## Results

No performance measurements were made — implementation and acceptance checks
only.

After relocation, all eight detector groups reported `ok`: Boltz-2, the MPNN
family, AntiFold, IntelliFold PyTorch (v2-flash and full v2), OpenFold-3,
LASErMPNN, AlphaFold 3, IntelliFold JAX (v2-flash and full v2), and
RFdiffusion3. The AF3 file copied into the promoted root retained SHA-256
`8be886bf5a798e4bbaeee3af14ba4c827674041f44b71fadccee2dd6020dd1c7`.

RFdiffusion3's own check passed MLX Metal, PyTorch MPS, FHE CCD, the official
checkpoint checksum and the exported MLX weight checksum. Every repaired Python
interpreter reported a `sys.prefix` beneath the promoted root, and no text
wrapper or package metadata beneath its venvs retained the old
`.iproteinstudio_freshtest` path.

`swift build` passed and `build_app.sh` produced the release app. The release app
launched from the clean clone, staged a byte-identical updated setup script into
the promoted runtime, and its detector reported every component ready.

## Decision and rationale

**Keep navigation available; gate only the destructive action.** Looking at a
form or another run's results consumes no GPU. Starting a second campaign is the
unsafe operation, so the Start buttons enforce mutual exclusion and the router
does not imprison the user.

**Use one production runtime after acceptance.** Keeping the complete install
under a test-only name made the GUI appear broken and encouraged divergent
state. Promotion preserves the clean-install evidence while making that exact
payload the runtime Finder launches use. The prior runtime remains a recoverable
backup until the GUI campaigns have been accepted.

**Repair every environment layout.** The main venvs live under `venvs/`, but
RFdiffusion3 owns `rfd3/.venv`; repairing only the first layout made a promoted
installation look healthy while RFdiffusion3 console scripts still named the
old root.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

swift build
./build_app.sh

NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
  bash Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh --repair-venvs

NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
  bash /Users/thomasfryer/.iproteinstudio/setup_pipeline.sh --detect

NANOHUNTER_ROOT=/Users/thomasfryer/.iproteinstudio \
MPLCONFIGDIR=/Users/thomasfryer/.iproteinstudio/matplotlib_cache \
  /Users/thomasfryer/.iproteinstudio/rfd3/install_rfd3.sh --check

open -n /Users/thomasfryer/iProteinStudio/build/iProteinStudio.app
```

## Limits and what was not tested

- A real campaign was not started merely to hold the router in a running state;
  therefore the mutual-exclusion button state was compiled and inspected but
  not exercised during costly live GPU work.
- macOS denied this automation process Accessibility and Screen Recording
  permission. The release app launched and its process/runtime state was
  verified, but scripted clicking and screenshots were not possible. A human
  GUI click-through remains required.
- The promoted engines passed detection and RFdiffusion3 passed its full
  self-check. This pass did not repeat the inference matrix already recorded in
  entry 0013.
- The dated prior runtime has not been deleted. It is retained deliberately
  until the promoted runtime passes the manual GUI campaigns.

## Next

1. In the already-built app, click RFdiffusion3, Predict and Iterative design in
   both idle and active-run states and confirm the selector remains present.
2. Run one small bundled-scaffold nanobody campaign through the GUI.
3. Run one minimal RFdiffusion3 protein campaign through the GUI, then remove
   the dated runtime backup only after both campaigns succeed.
