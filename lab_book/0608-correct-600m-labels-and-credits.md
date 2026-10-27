---
entry: 0608
title: Correct 600M capability labels and scientific credits
date: 2026-10-27
author: Codex
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [esmfold2, documentation, ui, attribution]
---

## Context

Following [[0586-integrate-esmfold2-600-release]], the user correctly rejected
labelling ESMFold2Fast-600M experimental because it does not support affinity
scoring, X-token initialization or templates. Those are capability boundaries.

## What was done

Removed the blanket 600M experimental/beta classification from current README,
CLI/model documentation, operating skill and evidence reference, MCP guide text,
engine metadata, installer text and app descriptions. Corrected the same model
classification in the existing 0.2.28 GitHub release notes; release-channel beta
status and existing binary assets are unchanged. Unsupported capabilities
remain enforced; actual qualification limits remain explicit. Historical lab
records, checkpoint identities and compatibility keys retain their provenance.
This entry supersedes their wording as a description of current model status.

Expanded README acknowledgements across the integrated predictors, design
methods, sequence designers, screening/scoring methods, model authors, MLX
ports and supporting scientific/UI infrastructure. Links trace to primary
projects; corrected Protein Hunter attribution to Griffin Rangel and credited
Geoffrey Taghon for the OpenFold3 MLX port. Third-party notices were updated
without changing licence text or model terms.

## Results

No performance measurements — wording and metadata correction only.

- `swift build`: passed.
- Existing `Tests/test_esmfold2_600_beta.py`: all 13 tests passed using the
  installed ESMFold2 runtime, covering installation, encoder mapping, profiles,
  capability rejection and refinement/schema routing.
- Shipped skill quick validation: passed.
- `git diff --check`: passed.

The default/control Python environments lacked PyYAML, so an initial test and
skill validation attempt failed at import. Repeating with the installed
ESMFold2 runtime passed; no dependency or scientific implementation was changed.

## Decision and rationale

Describe supported functions and measured limits independently. An absent
binding-affinity head is not evidence that a structure predictor is experimental.
Do not claim a new accuracy or hardware qualification merely by changing a label.
Keep existing model identifiers and historical experiment records intact.

## Reproduce

From the repository root:

```bash
swift build
"$HOME/.iproteinstudio/venvs/NanoHunter_esmfold2/bin/python" Tests/test_esmfold2_600_beta.py
git diff --check
```

## Limits and what was not tested

No model inference, new benchmarks, whole-model CUDA parity, biological efficacy
or physical 16 GB Mac test was performed. Weights, model arithmetic, numerical
settings and supported workflow routes are unchanged. This source/documentation
correction does not replace the already published 0.2.28 binary assets.

## Next

Ship the corrected app strings with the next packaged app update; retain the
existing qualification evidence and explicit capability boundaries.
