---
entry: 0323
title: Repair the broader workflow test fixture and profile expectations
date: 2026-10-06
author: Codex
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [tests, rfd3, protenix, prediction-settings]
---

## Context

Following 0322, the user asked to fix the broader workflow test failure rather
than leave it as a limitation. A fixture is the sample input a test constructs.
The ligand campaign fixture lacked `nanohunter_root`, which the real campaign
preparer supplies (`Resources/rfd3/prepare_campaign.py`). The runner requires
that root to load shared prediction profiles.

## What was done

Only `Tests/test_workflow_pipelines.py` changed:

- Supplied the fixture's pipeline root, derived from the test's repository path.
- Isolated the fixture's process-wide profile activation with `patch.dict` and
  asserted that the original environment is restored afterwards.
- The next failing assertion still required the old Protenix Constraint
  10-recycle/200-step default. Lab Book 0234 records promotion of the shared
  25-step default. Updated coverage to verify both the current 10/25 default and
  an explicit 10/200 override. Retained checks for explicit parameters and
  disabled TFG guidance; did not remove or bypass the assertion.

No production settings, model behavior, installed app or active job changed.

## Results

- Complete `test_workflow_pipelines.py`: PASS, exit 0.
- `test_prediction_profiles.py`: 9 tests PASS, exit 0.
- `git diff --check`: PASS.

The workflow log includes expected PBFAIL messages from deliberate invalid-input
cases. The final PASS and exit 0 confirm those rejection checks succeeded.
Logs are in `lab_book/artifacts/0323-repair-workflow-test-fixture/`.
No performance measurements.

## Reproduce

Using the managed Boltz Python environment with the required CPU dependencies:

```bash
~/.iproteinstudio/venvs/NanoHunter_boltz/bin/python Tests/test_workflow_pipelines.py
~/.iproteinstudio/venvs/NanoHunter_boltz/bin/python Tests/test_prediction_profiles.py
```

## Limits and what was not tested

These are CPU contract tests, with inference stages replaced by test doubles
where declared in the existing harness. No GPU inference, efficacy benchmark,
app deployment or full repository-wide suite was run. Swift was unchanged;
the successful build from 0322 remains the latest feature build.
