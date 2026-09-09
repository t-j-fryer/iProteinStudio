---
entry: 0108
title: Add a Protein Hunter design-engine checklist
date: 2026-09-08
author: Codex
type: implementation
status: complete
machine: Apple Silicon, local macOS developer machine
tags: [ui, predictors, recovery, scheduling]
---

## Context

The user requested multiple design engines in Protein Hunter, each receiving
the specified settings and full trajectory count. Previously the native form
selected one driver. Independent post-checkers are a different control and must
continue to exclude the model that designed the campaign being checked.

## What was done

- Added an optional `designPredictors` checklist to `DesignRequest`. Missing data
  retains the historical `designPredictor`; an explicitly empty checklist cannot
  run. Duplicate entries do not multiply work; retired selections fail visibly.
- Exposed engine checkboxes in Quick and Advanced, with installed/targeting
  compatibility constraints. Renamed the budget to Trajectories per engine and
  displayed per-engine and total trajectories, optimized cycles and seed folds.
- Projected one request per engine, preserving shared scientific settings,
  full trajectory count and existing engine-specific scheduler arguments.
  A batch records one common random base seed. Post-check lists are filtered
  separately per engine; the UI lists effective checkers for each campaign.
- Prepared every engine's inputs and immutable pipeline snapshot before
  submitting a single `desktop_iterative_batch` managed job. The broker
  preflights every child and fingerprints all child inputs/scripts. Engine
  campaigns run sequentially under the existing shared execution lease.
- Added per-engine artifact receipts, Stop/Resume behavior, partial-engine
  checkpoint reuse, and repair after interruption between receipt/manifest
  writes. A completed engine is skipped only after its result hashes validate.
- The live dashboard follows the active engine; Activity has separate campaign
  results and a Resume batch action. Completed engines remain completed when a
  later engine fails, and unstarted engines are identified as pending.
- Added usage/recovery documentation in `docs/PROTEIN_HUNTER_ENGINES.md`.
  Native bridge contract is 14 / 1.8.0. Public single-engine CLI/MCP request
  contracts remain unchanged. Packaged app build 25.

## Results

No measurements — implementation only. No scheduling defaults or performance
claims were promoted.

- Six broker tests run actual managed worker processes with inert engine
  scripts. They cover complete preflight, full-budget validation, ordered
  execution, failed-middle-engine resume, Stop preventing later engines,
  completed-output corruption, manifest repair, foreign/duplicate paths and
  changed later-engine code blocking the entire plan.
- Swift request/command contracts pass: old request migration, checklist
  persistence, full per-engine budgets, summed totals/estimates, unique engines,
  empty and retired selection rejection, targeting compatibility across all
  engines, per-engine check independence and resident/cycle-wave selection.
  Existing Predict, NISE, core, results and iterative harnesses pass.
- Desktop job contracts pass (10); MCP bridge contracts pass (17), including
  its localhost gateway with host permission. Existing iterative CLI and UI
  contracts pass. The UI wording assertion was updated for the new plural
  scheduler explanation; the scheduling checks were retained.
- Native controller harness passes: it executes production `RunController`,
  `TemplateWriter`, `CommandBuilder` and manifest serialization with temporary
  runtime paths and a stubbed submission boundary. It verifies one batch
  submission, complete inputs for three campaigns, the full trajectory budget,
  shared recorded seed, active-engine dashboard routing and no submission when
  preparing a later engine fails.
- `swift build` and the production release build passed. Packaged resource and
  strict ad-hoc signature checks passed. ZIP/DMG SHA-256 checks and `hdiutil
  verify` passed; read-only mounted DMG contents matched all 388 built-app
  entries, including file hashes, permissions and symlinks. The packaged batch
  broker files also matched source. The test image was unmounted.
- Updated `build/iProteinStudio.app` and
  `build/unsigned-beta-0.2.0-25/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`.
  This is a local dirty-tree beta; it was not published.

## Decision and rationale

Use one durable batch with separate engine campaigns, instead of submitting
jobs only as the app watches previous jobs finish. This allows the entire batch
to survive app closure and avoids losing the remaining selected engines on a
client crash. Retain each existing scientific runner and its worker lifecycle;
do not introduce competing GPU model owners or change trajectory arithmetic.
Keep independent checking per campaign rather than globally excluding every
selected design engine, which would remove useful cross-model checks.

## Reproduce

```bash
python3 Tests/test_iterative_engine_batch.py
python3 Tests/test_desktop_jobs.py
python3 Tests/test_mcp_bridge.py
python3 Tests/run_swift_contracts.py
bash Tests/test_iterative_cli_contract.sh
bash Tests/test_iterative_results_ui_contract.sh
swift build
release/release_app.sh --unsigned-beta --allow-dirty
```

## Limits and what was not tested

No fresh neural-inference campaign, target-specific scientific validation,
GPU memory soak or throughput measurement. Broker tests substitute only the
scientific executables with inert fixtures, while executing the real queue,
lease, subprocess, cancellation, provenance and recovery code. This establishes
software orchestration, not comparable scientific performance across engines.
No production workspace, running campaign, installed environment or model
weight was modified. Full interactive GUI/VoiceOver acceptance and second-Mac
installation remain unverified. No public publication or notarization.

## Next

Use a declared small real-model acceptance campaign before making
scientific-accuracy or new speed claims. Complete interactive GUI/VoiceOver
acceptance in a session with accessible windows.
