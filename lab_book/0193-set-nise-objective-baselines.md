---
entry: 0193
title: Set explicit NISE sequence-objective early baselines
date: 2026-09-25
author: Codex
type: implementation
status: complete
machine: Local Apple-silicon development Mac; no inference benchmark
tags: [nise, nesso, psichic, ui, mcp]
---

## Context

Follows [0192](0192-add-nise-objective-choice.md). The user explicitly requested
NESSO 0.4 and PSICHIC 0.2 instead of the initial off/zero early gates.

## What was done

Updated Swift new-request defaults, Python contract, MCP schema/catalog, UI help
and NISE documentation. The inclusive cutoff applies only at cycle01 after
geometry eligibility, to the selected complete objective: NESSO P(bind) + 1 -
entropy_crop_pl, or PSICHIC 1 - predicted_nonbinder. Zero still disables the gate.
Explicit saved settings persist. Saved objective requests missing these fields
retain historical zero gates; older Boltz-only cohort imports receive the new
baselines when the user selects objective mode.

Explained the existing exact Boltz bound ligand_pLDDT/100 + 1. Candidates are
pruned only strictly below the relevant eligible lineage/seed/beam boundary;
ties are scored. Sequence-objective mode never runs the Boltz affinity head.
Its configured shortlist is folded before selection; ordered early termination
of structure generation was not added or implied.

## Results

64 Python NISE tests passed; targeted Swift request/migration harness passed.
No measurements — implementation only. Release Swift build, resource-bundle
contract, deep strict signing verification, packaged source equality and DMG
verification all passed. The local ad-hoc-signed development artifact is
`build/transfers/iProteinStudio-NISE-baselines.dmg`, version 0.2.6-cohort3 (52).
This is not a published/notarized release.

## Decision and rationale

Use the user's explicit independent baselines rather than inventing a conversion
from Boltz 0.80. These thresholds are not biologically calibrated probabilities.
Preserve resumed campaign semantics rather than silently changing saved gates.

## Reproduce

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" -m unittest discover -s Tests -p 'test_nise_*.py'
```

Local release build uses the native SwiftPM workaround recorded in 0191 and
version 0.2.6-cohort3 (52). Logs are in artifacts/0193-nise-baselines/.

## Limits and what was not tested

No neural-model inference, biological threshold calibration, GPU performance
measurement, receiving-Mac execution or GUI interaction test. No change to the
running biotin campaign or installed app; no GitHub publication or commit.
Existing portable cohort scientific data are unchanged and import-compatible.

## Next

Prospective evaluation can establish whether these user-selected cutoffs retain
sufficient diversity and geometry-passing designs.
