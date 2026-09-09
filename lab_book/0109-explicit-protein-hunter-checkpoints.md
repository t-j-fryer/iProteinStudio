---
entry: 0109
title: Expose OpenFold-3 and explicit IntelliFold design checkpoints
date: 2026-09-08
author: Codex
type: implementation
status: complete
machine: Apple Silicon, local macOS developer machine
tags: [ui, predictors, recovery]
---

## Context

Following entry 0108, the user requested OpenFold-3 and separate Flash/Full
IntelliFold design options. OpenFold-3 was supported by the scientific runner
but omitted from the native design list. IntelliFold used one shared model
setting, which could not express both checkpoints in one batch.

## What was done

- Added a design-specific `DesignEngine` identity, separate from `Predictor`'s
  backend identity. The checklist now includes OpenFold-3, IntelliFold v2 Flash
  and IntelliFold v2 Full, including simultaneous Flash/Full selection.
- Added optional explicit `designEngines` persistence. Older single-engine and
  build-25 backend checklists derive their previous checkpoint from the saved
  model field. An old Full selection does not silently become Flash.
- Projected every explicit design choice into its own existing single-engine
  runner contract. IntelliFold saves `--model v2-flash` or `--model v2`;
  OpenFold saves `--predictor openfold-3-mlx`. Campaign directories have distinct
  method names and every choice retains the full trajectory budget.
- Checking-model selection is now explicitly labelled and separate from design
  checkpoint selection. Both IntelliFold checkpoints share the same independent
  checking identity. No Flash timing is presented as a Full time estimate.
- Preserved model-installation guards and template restrictions: Full requires
  its optional checkpoint and shared runtime; OpenFold remains incompatible
  with this workflow's Guide PDB/CIF templates. History describes the saved
  design checkpoint.
- Confirmed the existing resident worker consumes the selected IntelliFold
  model flag; reused the existing OpenFold design and resident routes. No
  science code, scheduler defaults or public CLI/MCP schemas changed.
- Updated the engine guide and packaged app build 26.

## Results

No measurements — implementation only.

- `swift build` passed.
- Swift contract suite passed, including the native controller writing a
  Flash/Full/OpenFold batch, three distinct campaign folders, complete budgets,
  explicit backend/model arguments and correct Full-model dashboard context.
- Request contracts passed for explicit-checkpoint persistence, legacy Full
  migration, same-family checking exclusion, required installations, removal
  of Full without losing Flash, preserved checking-model selection and
  resident scheduling for all three choices.
- All six durable broker batch tests passed. Existing iterative CLI and UI
  contracts passed.
- Release build, packaged-resource checks and strict ad-hoc signature verification
  passed. ZIP/DMG SHA-256 checks and `hdiutil verify` passed. The read-only mounted
  DMG matched all 388 built-app entries, including hashes, modes and symlinks;
  the disk image was unmounted.
- Outputs: `build/iProteinStudio.app` and
  `build/unsigned-beta-0.2.0-26/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`.
  This is a local dirty-tree beta, not a published release.

## Decision and rationale

Use design-method identities instead of introducing duplicate backend identities
in Predict and checking. The scientific backend is still IntelliFold; the
checkpoint is a separately saved design choice. Keep every campaign on its
existing scientific runner, with explicit model flags, rather than adding a
second folding implementation or sharing mutable model selection across jobs.

## Reproduce

```bash
python3 Tests/run_swift_contracts.py
python3 Tests/test_iterative_engine_batch.py
bash Tests/test_iterative_cli_contract.sh
bash Tests/test_iterative_results_ui_contract.sh
swift build
release/release_app.sh --unsigned-beta --allow-dirty
```

## Limits and what was not tested

No new real-model inference, accuracy comparison, speed benchmark, memory soak,
installation or model download. Native tests replace submission/runtime paths
with fixtures; broker tests run real workers with inert scientific executables.
No active campaign, installed runtime or model weight was modified. Interactive
GUI/VoiceOver and second-Mac acceptance remain unverified. No public release,
Developer ID signing or notarization.

## Next

Use a declared bounded real-model campaign before claiming new
scientific-accuracy or throughput results.
