---
entry: 0042
title: Complete the Protenix Constraint install and documentation contract
date: 2026-08-27
author: GPT-5.6
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [protenix, install, reproducibility, documentation, mps]
---

## Context

The direct `--with-protenix-constraint` path added in
[[0040-protenix-constraint-pocket-engine]] already created an isolated native-MPS
runtime and verified checkpoint. The surrounding product contract had not been
audited after integration. README and CLI engine lists omitted it, onboarding
described every optional component as a post-prediction checker, and the
existing-install reuse/materialisation lists did not carry the constraint venv,
source or model directory.

## What was done

- Kept the checkpoint as a separate opt-in from Protenix v2/Mini and documented
  the exact design-only, protein-only, ESM-free, no-CPU-fallback boundary.
- Added `setup_pipeline.sh --help`, including the constraint flag and scope.
- Added `NanoHunter_protenix_constraint`, `ProtenixConstraint` and
  `protenix_constraint` to component reuse and materialisation.
- Expanded materialisation source discovery so a constraint-only linked source
  can have editable-install paths relocated correctly.
- Corrected first-run copy: optional components are not all independent
  checkers, and the recommended default is distinct from experimental engines.
- Updated README, CLI and architecture documentation with installation,
  checkpoint verification, 8 Å token-centre semantics, validated 10 × 200 run
  profile, independent re-fold requirement, storage and removal.
- Added a no-network installer contract that links a synthetic existing
  constraint runtime, detects it, materialises it, and confirms all three
  managed directories become self-contained.

The app bundle already copies the complete `Resources/pipeline` directory, so
the patch and dependency lock are staged on every launch. The installer verifies
the real 1,475,206,741-byte checkpoint and its SHA-256 before writing an install
receipt; no weights are committed to this repository.

## Results

No performance measurements — installer and documentation work only.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Synthetic constraint reuse/materialisation | 1 | installer contract | pass |
| Bundled patch and dependency lock | 2 assets | present and non-empty | pass |
| Release app resource bundle | 1 build | installer, patch and lock packaged | pass |
| Existing managed Protenix runtimes | 2 components | detector state | both `ok` |

## Decision and rationale

The constraint model is not a third identity inside the v2/Mini component. Its
checkpoint lacks the trained ESM projection and therefore requires a different
strict-load configuration and dependency surface. A separate component makes
that scientific distinction visible, prevents environment cross-contamination,
and lets users remove the experimental checkpoint without deleting v2/Mini.

We rejected making it part of the recommended default. The current pocket-only
acceptance showed weak steering, so automatic multi-gigabyte installation would
overstate maturity and waste disk for users who only need prediction.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
caffeinate -dimsu bash Tests/test_installer_component_contract.sh
caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_protenix/bin/python Tests/test_workflow_pipelines.py
caffeinate -dimsu swift build
caffeinate -dimsu bash build_app.sh
```

## Limits and what was not tested

The real checkpoint was not downloaded again: its installed native-MPS GPU
acceptance and exact hash/size are recorded in 0040. The new regression uses
small synthetic files to exercise component wiring without network or multi-GB
downloads. A clean Mac with no prior Python/Homebrew state remains a release
acceptance gap until a disposable Apple-Silicon machine is available.

## Next

Run the complete first-launch GUI flow on a clean Apple-Silicon user account and
retain the setup log as release evidence before promoting the checkpoint beyond
experimental status.
