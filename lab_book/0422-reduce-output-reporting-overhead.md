---
entry: 0422
title: Reduce CPU output-reporting overhead
date: 2026-10-14
author: Codex
type: implementation
status: complete
machine: macOS 26.6.1 arm64, 16 reported logical CPUs, Python 3.12.10; no GPU inference
tags: [performance, predictors, reporting]
---

## Context

Follow-up to [0421](0421-review-geometry-cpu-overhead.md). User authorized
surrounding CPU/orchestration improvements while leaving MPNN unchanged.
This change addresses reporting overhead, not the search algorithm or model settings.

## What was done

- `validate_prediction_geometry.py`: fast tokenization for unquoted ASCII
  mmCIF atom rows, retaining shlex for quoted/escaped fields. A process-local,
  32-entry inspection cache is keyed by coordinate SHA-256, format and diagnostic
  thresholds. Every call reads/hashes current bytes; same-size/timestamp edits and
  symlink retargeting invalidate reuse. Cached dictionaries are copied for callers.
  Reports hash the same byte snapshot that was parsed.
- `resident_predictor.py`: call the common report/validation function directly,
  eliminating its validator subprocess and sharing inspections within the resident
  interpreter. Unusable coordinates remain fatal; distance diagnostics remain advisory.
- `prediction_output_reporting.py`: batch normalization, existing relative-link
  policy, geometry reports, confidence extraction and timing-file writes in one
  CPU process. Preserve key precedence, report paths, timing values and file formats.
  An explicit 2–4-worker option supports offline qualification; the runner uses one.
- `nanohunter_run.sh`: invoke the batch reporter once per predictor batch and
  collect confidence metrics once per recording wave. MPNN, seeds, model settings,
  inference scheduling and numerical scoring were not edited.
- Added ten CPU-only regression tests and registered geometry/reporting tests in
  the fast suite. Updated the packaged-resource assertion for the new helper.
  Corrected existing test fixtures: missing shell environment variables and a
  JSON-backed YAML stub that lacked `safe_dump`.

The MCP snapshot captures the entire scripts directory, so the new helper is
covered by existing immutable code provenance. No runtime deployment, app rebuild,
job migration or job launch was performed. Existing frozen jobs retain their code.

## Results

CPU-only paired benchmark of the actual shell normalization/recording functions:
12 identical synthetic outputs per batch, 400 residues and four atoms per residue;
five paired replicates with alternating execution order. Inference is stubbed.
Before-source snapshots and exact source hashes are retained with the measurements.
All resulting files—including metrics, geometry, timings and exports—were identical
after fixture-root path normalization in every paired replicate.

| Reporting path | Paired replicates | Median wall seconds per 12-output batch |
|---|---:|---:|
| Before | 5 | 5.175 |
| After | 5 | 1.910 |

This is a **63.1% reduction in the tested CPU reporting stage**, not a measured
reduction in inter-cycle gaps or complete campaign duration. Hardware identity is
limited to the platform/CPU count reported above: sandboxed `sysctl` identification
was denied. Background load was not controlled; `host_timing_qualified=false`.

For the new finalizer alone, medians across five repeats were 0.140 s (one worker),
0.246 s (two), and 0.240 s (four). Process-pool startup outweighed parallelism for
this fixture. Keep one worker rather than raising CPU concurrency without evidence.

Executed checks: 42 passing unittest cases across output reporting, geometry,
prediction safety, resident resume, live results, code snapshots and NISE batch
adapters; two managed-environment-dependent resume tests skipped. Storage-policy
checks and the iterative CLI contract passed. Shell syntax also passed, separately
from those execution tests. The measured-source/hash audit passed.

## Reproduce

```bash
python3 Validation/experiments/output_reporting_overhead_v1/benchmark.py
python3 Tests/test_output_reporting.py
python3 Tests/test_geometry_reporting.py
python3 Tests/test_prediction_engine_safety.py
python3 Tests/test_resident_prediction_resume.py
python3 Tests/test_live_iterative_results.py
python3 Tests/test_code_snapshot.py
python3 Tests/test_nise_stage_batches.py
python3 Tests/test_storage_policy.py
bash Tests/test_iterative_cli_contract.sh
```

Manifest: `Validation/experiments/output_reporting_overhead_v1/manifest.json`.
Measurements, audit and original-source control:
`Validation/output/output_reporting_overhead_v1/`.
Base commit: `25b3eb92dae59b4f4e48f3f10f7d6b8607faeb3d`; working tree already contained
other work, so the benchmark's source hashes/snapshots, not HEAD alone, define it.

## Limits and what was not tested

No GPU run, complete campaign timing, all-engine integration run, real managed
Accelerate/PyYAML resume test, memory soak, Swift build or packaged-app execution.
The parallel path was tested for byte-equivalent outputs, not qualified alongside
live inference. No manuscript performance claim was changed. Input preparation,
shell export subprocesses and GPU/CPU overlap remain separate opportunities.
The cache avoids repeated parsing only within an interpreter, not across processes.

## Next

Qualify the updated source through the normal preflight/job snapshot on a small
existing benign fixture before adopting it for a new scientific campaign. Measure
whole-cycle wall time and memory with unchanged inputs/settings; do not extrapolate
the 63.1% reporting result into a campaign speedup.
