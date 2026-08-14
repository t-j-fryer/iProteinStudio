---
entry: 0017
title: Constrain Boltz-only prediction options
date: 2026-08-14
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, prediction, boltz, validation]
---

## Context

The Predict tab presented steering potentials and small-molecule binding-strength
prediction beneath the engine list, but left both controls interactive when the
batch contained only IntelliFold, AlphaFold 3 or OpenFold-3. The launch script
only applies potentials to a predictor named `boltz`, while the affinity property
is meaningful only to Boltz and only for a fold containing a ligand. The visible
state therefore implied capabilities the selected engines do not have.

## What was done

- Grouped both switches under an explicit `Boltz-2 options` heading.
- Disabled both controls unless Boltz-2 is among the selected engines.
- Disabled binding strength until the parsed jobs contain a small molecule.
- Added context text and accessibility hints that explain why each option is
  unavailable and clarify that, in a multi-engine batch, the settings affect
  only its Boltz portion.
- When Boltz is deselected, immediately clear both Boltz-only values. Parsing a
  protein-only batch also clears a stale binding-strength selection.
- Normalise old saved projects when the Predict form appears.
- Added model validation and controller-side launch sanitisation so a stale or
  programmatically constructed request cannot pass the flags to an incompatible
  batch even if it bypasses the controls.

## Results

No performance measurements — UI and launch-contract bugfix only.

A direct model test covered three states: non-Boltz options are cleared; Boltz
potentials remain selected for a protein batch while affinity is cleared; and a
mixed-engine Boltz + ligand batch retains both options. `swift build` passed.

## Decision and rationale

**Allow Boltz-specific settings whenever Boltz is included, not only when it is
the sole engine.** Predict intentionally supports orthogonal multi-engine
batches. In that case the switches apply to Boltz while the other engines keep
their defaults, which the interface now says explicitly.

**Constrain at the model and launch boundary as well as the UI.** Disabling a
checkbox fixes new interaction but not a project saved by an older build.
Normalisation makes state understandable, validation makes mistakes visible,
and config sanitisation is the final guard against invalid execution.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache swiftc \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/PredictionRequest.swift \
  /private/tmp/iproteinstudio_prediction_option_test/main.swift \
  -o /private/tmp/iproteinstudio_prediction_option_test/run
/private/tmp/iproteinstudio_prediction_option_test/run

swift build
./build_app.sh
```

## Limits and what was not tested

- No new GPU fold was launched because the scientific backend and its command
  were not changed; this pass tests option eligibility and generated-config
  protection.
- The final GUI was inspected through macOS Accessibility and screenshots, not
  through a complete external-user VoiceOver task.
- No claim is made here about whether steering potentials improve a particular
  target; the prior measured and scientific evidence remains in earlier entries.

## Next

Apply the same capability-gating pattern whenever a future engine-specific
option is added: visible scope, immediate state normalisation, validation and a
launch-boundary guard.
