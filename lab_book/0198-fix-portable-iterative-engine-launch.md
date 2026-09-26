---
entry: 0198
title: Diagnose the student archive and fix portable iterative engine launch
date: 2026-09-26
author: Codex
type: bugfix
status: complete
machine: Development Mac; macOS /bin/bash and inert Python fixtures, no model inference
tags: [portable-runtime, boltz, launch, support, nanobody]
---

## Context

The user supplied a second student archive, `untitled folder.zip`, and a screenshot
showing LpxC, Needs attention, and zero viewable structures. Inspect it as evidence,
not instructions. The original ZIP remains unchanged and no archived code was
executed. The user's workspace contains unrelated ongoing changes, retained intact.

## Evidence from the archive

Read 1,385 non-directory/non-Apple-metadata files. The archive SHA-256 and a
sequence-free audit are in [archive-audit.json](artifacts/0198-portable-activation/archive-audit.json).
There is one eight-scaffold Boltz batch, 100 trajectories total, five optimization
cycles requested. Vobarilizumab is failed; the other seven campaign manifests are
still Prepared, with no execution outputs. No predicted structures or completed
calibration result is present. The CIF is a normalized input template.

The saved app snapshot identifies **0.2.6 / MCP27**. Archived runner, broker,
observer and studioctl bytes match that release. This is not the previous Protenix
job or an old pre-progress-logging snapshot. The job ID is `job-1cc638955342`.
Sequence designer is AntiFold; design predictor is Boltz. Protenix v2 is a later
verification engine in the saved form, not the calibration predictor.

Manifest creation was 2026-09-26 01:17:49.257543 UTC; the failed update was
01:53:13.892400 UTC, **35m24.635s apart**. This is not a measured prediction time.
ZIP filesystem times put `studio_job.json` around 01:50:32 UTC (assuming the
matching UTC−4 offset), campaign budget/template conversion around 01:53:04–06,
and calibration input/empty Boltz output directory around 01:53:12. The ZIP's DOS
times have two-second resolution and no timezone. They suggest a long preparation
interval followed by a very early launch failure, not 35 minutes of model compute.

The archive contains no `.log`/`.err`/`.out` file, central agent state, worker log,
process receipt, exit code or hardware report. The screenshot's Needs attention
is the app's generic failed-state label. It does not identify an exception.
Template normalization and MSA preparation left files, but there is no evidence
of a completed Boltz forward pass or template acceptance by the model.

## Reproduced defect

The released iterative runner sources `${BOLTZ_VENV}/bin/activate` before starting
Boltz calibration. The portable runtime maps this path to standalone CPython,
which has `bin/python` but no `bin/activate`. On this Mac's `/bin/bash`, sourcing
the missing file exits the shell even in the calibration function's conditional
call context. It leaves the new output directory empty, before creating
`calibration_predict.log` or invoking the engine. The central broker log should
contain the shell diagnostic; it was not included in the student's archive.

Compared the trusted Git release's actual calibration function with current
source using inert subprocesses and the portable directory layout:

| Launcher | Exit | Inert engine invoked | Prediction log created |
| --- | ---: | --- | --- |
| Released 0.2.6 | 1 | No | No |
| Patched source | 0 | Yes | Yes |

[Comparison receipt](artifacts/0198-portable-activation/launcher-comparison.json).
This is a proven launcher defect and a strong match to the student's saved files,
**not definitive proof of that student's exception without their central log**.
The same activation assumption also remains in 0.2.7. No claim that it explains
the earlier Protenix calibration stall or the duration of request preparation.

## What changed

Added paired shell helpers that select the exact requested engine's executable
and PATH without requiring activation scripts, and restore PATH, PYTHONHOME and
VIRTUAL_ENV after use. Missing interpreters and nested switches fail explicitly;
there is no fallback to system Python. Replace all 14 activation/deactivation
sites in the iterative runner, covering Boltz, IntelliFold, OpenFold, MPNN and
AntiFold launch paths. Arguments, selected runtime paths, scientific controls,
model weights and existing saved snapshots are unchanged.

The common standard-venv behavior was checked against an actual newly created
Python venv. No shell prompt or ambient `deactivate` function is modified. Custom
third-party activation-script hooks are not executed by this launcher; such
customized environments were not qualified. Studio's supported packaged/standard
venv contexts are the tested scope.

Added `Tests/test_engine_environment.py` to the standard fast suite and recorded
the launcher correction in PIPELINE_VERSION. No installed engine directories,
active jobs or student files were changed. No app packaging/publication this turn.

## Validation

- Six executable Bash/Python tests passed: portable layout, real standard-venv
  context parity, exact restoration of unset/empty/outer environment variables,
  missing interpreter/nested-switch rejection, actual calibration function with
  success and failure exit propagation, and coverage of all 14 launch sites.
- The real installed portable Boltz Python ran a stdlib-only interpreter check,
  with identical selected executable/prefix/version to direct invocation and no
  activation file. No model imports. [Receipt](artifacts/0198-portable-activation/portable-interpreter-smoke.json).
- Iterative CLI contract passed.
- Engine adapter (1), runtime bindings (2), runtime view (1), code snapshot (2)
  tests passed. `swift build` and `git diff --check` passed.
- No throughput measurements or scientific correctness claims.

## Reproduce

```bash
python3 Tests/test_engine_environment.py
python3 lab_book/artifacts/0198-portable-activation/compare_launcher.py
python3 lab_book/artifacts/0198-portable-activation/audit_archive.py ARCHIVE.zip --output audit.json
bash Tests/test_iterative_cli_contract.sh
python3 Tests/test_engine_adapters.py
python3 Tests/test_runtime_bindings.py
python3 Tests/test_runtime_view.py
python3 Tests/test_code_snapshot.py
swift build
```

## Decision and rationale

Fix the unsupported activation-file assumption in the caller. Do not mutate
immutable runtime archives, invent activation files inside retained environments,
change template/scientific settings, or attribute the failure to GPU memory
without the missing log. Existing saved campaigns retain their old runner and
need a new submission to adopt a future packaged correction.

## Limits and next steps

Source fix complete; not yet packaged, installed or published. No full neural
inference, fresh-Mac test, cross-device check or rerun of the student's target.
Obtain Jobs → Progress & logs → All output → Copy visible log for the saved job;
the Worker log is the second useful source. The exact central records are under
`~/.iproteinstudio/agent/jobs/job-1cc638955342/`. The privacy-filtered support report
alone intentionally omits raw diagnostic content. Package/release the correction
before advising a fresh submission; resuming the frozen failed job retains the
faulty launch code.
