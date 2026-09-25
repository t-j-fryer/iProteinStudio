---
entry: 0188
title: Add engine progress logging
date: 2026-09-25
author: Codex
type: implementation
status: complete
machine: Local development Mac; synthetic process tests, no engine benchmark
tags: [logging, jobs, predictors, progress, support]
---

## Context

[0187](0187-inspect-student-run-archive.md) found a roughly twenty-minute gap
between Protenix's last input-preparation message and cancellation. Existing logs
could not distinguish computation from a hang. The user requested progress logs
across all integrated engines.

## What was done

Added stdlib-only `scripts/engine_progress.py` and a job-scoped Python bootstrap.
The managed broker enables them from retained pipeline code, preserving immutable
Resume behavior. Lazy import observers wrap known engine methods without changing
their arguments, return objects, exceptions or tensor computation. Engine-specific
milestones, call counters, elapsed times and PIDs are emitted to stderr and mirrored
to the main job log. A separate 30-second heartbeat says computation progress is
unknown. Nested stages restore their parent when they return, idle workers stay
quiet, and forked children reset inherited observer locks/threads.

Coverage includes all structure/backbone engines, NESSO/PSICHIC, MPNN variants,
LASErMPNN and AntiFold. PSICHIC restores only its trusted retained observer after
clearing inherited Python paths. Existing runtime startup customization is chained.
See [engine progress documentation](../docs/ENGINE_PROGRESS.md) for the exact
stage coverage and distinctions between host calls, heartbeats and GPU completion.

No modification to installed runtime sources, active processes, model weights,
scientific defaults, app high-level progress percentages or existing job outputs.
No application deployment or GitHub release was performed in this task.

## Results

No inference throughput or scientific-accuracy measurements were made.

| Check | Result |
| --- | --- |
| `Tests/test_engine_progress.py` | 14 passed: observer contracts, nesting, counts, real heartbeat thread, missing hooks, opt-out, old snapshots, live subprocess mirroring, clean JSON stdout, exception/exit preservation, unwritable log destination, duplicate suppression, existing startup policy, fork reset, broker integration |
| `Tests/test_desktop_jobs.py` | 19 passed, including cancellation of separate-process-group descendants and inherited execution leases |
| `Tests/test_code_snapshot.py` | 2 passed |
| `Tests/test_psichic_screen.py` | 4 passed |
| `Tests/test_engine_adapters.py` | 1 passed |
| `swift build` | Passed |
| Installed-source hook contract audit | Every registered class/method found in inspected installed source; includes both Protenix and ProtenixConstraint |

The source audit parsed Python ASTs without importing or running engine code. It
is supporting evidence, not an inference test. Runtime observer tests execute
synthetic model calls and subprocesses. Initial sandboxed broker tests failed
because `/bin/ps` was denied; Swift initially could not access its module cache.
Both suites/build passed with approved access, without changing the code to bypass
process-tree safeguards.

## Decision and rationale

Use narrowly listed lazy observers instead of forking each upstream model's
scientific loops or tracing every Python line. Do not force GPU synchronization
for logging, read tensor values, create fabricated percentages, or cancel a quiet
job automatically. A host return is labelled explicitly as not measuring GPU
completion. Mirror only these bounded records directly to the main job log instead
of refactoring all existing subprocess output contracts.

## Reproduce

```bash
python3 Tests/test_engine_progress.py
python3 Tests/test_desktop_jobs.py
python3 Tests/test_code_snapshot.py
python3 Tests/test_psichic_screen.py
python3 Tests/test_engine_adapters.py
swift build
```

The process lifecycle tests need permission to read macOS process listings; they
launch and stop only temporary synthetic workers, not real scientific jobs.

## Limits and what was not tested

No full model predictions, GPU numerical equivalence, overhead benchmarks,
fresh-Mac or cross-chip validation. Installed source contracts were inspected,
but real inference through every hooked runtime remains an acceptance test.
This does not diagnose or resolve the student's original calibration delay.
No percentages, per-input counter resets, GPU utilization, memory-pressure
diagnostics or prediction ETA are introduced. Compiled model execution paths were
not qualified; supported managed defaults are the intended scope.

The thread heartbeat can itself be delayed by native code holding the GIL, and
only reports while an observed method is active. Uninstrumented preprocessing and
downloads retain their existing logs. Direct external CLI launches do not opt in
automatically. Previously saved jobs keep their old frozen code and logging.

## Next

Observe logs on the next newly submitted, approved scientific smoke run, then
package the feature in a subsequent app release. Consider richer native progress
presentation only where the engine exposes reliable denominators.
