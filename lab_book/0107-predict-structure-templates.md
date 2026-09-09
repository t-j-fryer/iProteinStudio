---
entry: 0107
title: Add structure templates to Predict
date: 2026-09-08
author: Codex
type: implementation
status: complete
machine: Apple Silicon, macOS; local developer machine
tags: [predictors, ui, templates, recovery]
---

## Context

Predict did not expose the Guide template functionality already available in
Protein Hunter. The user requested the same capability in Predict. Existing
Protein Hunter behavior deliberately excludes design binder chain A; plain
monomer prediction must be able to select A explicitly.

## What was done

- Added a structure picker and explicit query-chain selection in both Quick and
  Advanced Predict. Imports retain the original filename inside a unique
  workspace directory; native runs copy the file again into their own inputs.
- Extended the backward-compatible request/configuration with optional Guide
  template settings. Blocks incompatible engines, missing files, missing query
  chains and inconsistent guidance of identical protein copies.
- Added `scripts/prediction_templates.py`, reusing existing Boltz normalization,
  IntelliFold local template preparation and Protenix v2 inline-mmCIF conversion.
  Explicit Predict chain scope permits monomer A; default design scope still
  excludes binder A. Unselected proteins remain untemplated.
- Preserved resolved MSAs and existing directory batch/concurrency scheduling.
  IntelliFold receives one combined local manifest per prepared batch; no extra
  template database is requested and no new residency mode is introduced.
- Added preparation receipts, interrupted-preparation archival and config/source
  fingerprints to reject stale guided results during resume. Native/MCP plans
  include template and adapter provenance; MCP imports an immutable artifact.
- Documented usage, engine limits and recovery in `docs/PREDICTION_TEMPLATES.md`.
  Updated MCP contract to 13 / bridge 1.7.0; packaged local app build 24.

## Results

No measurements — implementation only. Functional checks completed:

- Six synthetic-structure tests execute preparation for all three engines,
  actual Protenix conversion, manual MSA preservation, template receipts,
  corruption rejection, chain-A/design exclusion, identical-copy reuse and
  multi-input IntelliFold command routing. The real Predict driver and preparer
  run through first execution and resume with inert folding/geometry substitutes.
- Pure Swift harnesses pass, including new request migration/persistence and
  chain/engine constraints; existing NISE, core, results and iterative harnesses.
- Workflow pipeline contracts pass, including existing Protein Hunter template
  behavior. Prediction engine and MSA reliability suites pass (4 + 4 tests).
- Desktop job contracts pass (10), including native/MCP template provenance and
  imported-file checks. MCP bridge contracts pass (17).
- `swift build` and the release build passed. The packaged resource contract,
  strict ad-hoc signature verification, ZIP/DMG SHA-256 checks and `hdiutil
  verify` passed. The read-only mounted DMG matched the built app across 388
  entries, comparing file hashes, modes and symlink targets; it was unmounted.
- Outputs: `build/iProteinStudio.app` and
  `build/unsigned-beta-0.2.0-24/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`.
  This is a dirty-tree local test beta; no publication was attempted.
- An isolated app copy launched with a synthetic workspace and inert dependency
  markers. Accessibility inspection returned no window/control data, so this
  does **not** count as successful interactive GUI acceptance. The test app was
  closed; normal workspaces and model environments were not changed.

Initial test setup found that the RFdiffusion environment lacks Gemmi and Boltz
lacks Biotite. The existing Protenix environment has both and was used for this
CPU fixture suite; no environment was installed or modified. An inert fixture's
Python symlink lost virtual-environment context; an executable wrapper fixed the
fixture. The initial Swift harness had a throwing expression in a nonthrowing
assertion and was corrected. Sandboxed Swift compilation could not write its
standard module cache; the host-permission build passed. The MCP localhost test
needed host permission to bind its temporary loopback port, then passed.

## Decision and rationale

Port Guide behavior rather than inventing new restraint strength settings.
Require explicit selection because chain A means a monomer in Predict but a
binder in Protein Hunter. Retain the original design defaults and make Predict
scope explicit, avoiding a silent behavioral change to existing campaigns.
Preserve the directory batching contract instead of introducing a separate
model-launch path for each templated sequence.

## Reproduce

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" bash Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh --detect
MPLCONFIGDIR=/private/tmp/studio-template-matplotlib "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" Tests/test_prediction_templates.py
MPLCONFIGDIR=/private/tmp/studio-template-matplotlib "$HOME/.iproteinstudio/venvs/NanoHunter_protenix/bin/python" Tests/test_workflow_pipelines.py
python3 Tests/run_swift_contracts.py
python3 Tests/test_prediction_engine_safety.py
python3 Tests/test_prediction_msa_reliability.py
python3 Tests/test_desktop_jobs.py
python3 Tests/test_mcp_bridge.py
swift build
release/release_app.sh --unsigned-beta --allow-dirty
```

## Limits and what was not tested

No fresh neural inference, binding/design campaign, template accuracy comparison,
GPU memory soak or throughput benchmark. The synthetic PDB is a conversion
fixture, not a scientifically validated structure. Fixture folding/geometry
substitutes establish orchestration, not model acceptance or accuracy. No new
engine installation, weight download, public publication, Developer ID signing,
notarization, second-Mac installation or Sparkle upgrade acceptance.

## Next

A declared, bounded real-model acceptance campaign is needed before claiming
scientific accuracy or speed for the new Predict integration. Complete an
interactive picker/chain-selection check in a session with accessible windows.
