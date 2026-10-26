---
entry: 0517
title: Add optional memory admission and select a small motif pilot
date: 2026-10-22
author: Codex
type: implementation
status: complete
machine: Local Apple Silicon Mac; CPU tests, inert child processes and development build only
tags: [memory, mcp, ui, rfd3, motifs, beta]
---

## Context

User explicitly requested that memory admission be optional, with an override
for this motif study and memory measurements used to qualify future estimates.
They also requested an informative small benchmark subset rather than all cases.
Follows [[0457-add-memory-admission]] and [[0491-preserve-original-motif-correspondence]].
No instruction to start the proposed benchmark panel was inferred from the
request to recommend cases.

## What was done

- Added an off-by-default “Override memory check for new runs” preference in
  Settings → Memory, Predict and Atomic motif beta. Shared GUI submission copies
  the current choice before asynchronous planning. It applies across workflows;
  queued/resumed runs retain their immutable saved choice.
- Added top-level `memory_policy: enforce|override` to scientific MCP planners,
  including composed recipes/batches. Scoped context carries the explicit choice
  through nested planners without leaking into a later request. Normalized plans
  record the policy and original estimate/refusal reason; an override is labelled
  `overridden`, not `allowed`. Unknown estimates remain null.
- Dispatch re-evaluates memory and records the result while honoring the saved
  override. The managed worker passes its saved policy to child prediction
  checks. Model/input validation, MSA provenance, plan and code digests, process
  ownership, shared execution lock and scheduling remain active. No change to
  calibrated coefficients or model scientific settings.
- Added approximately one-second memory sampling to managed commands using the
  existing Validation collector's Darwin rusage_info_v2 counters. Records contain
  verified process-tree accounted footprint and RSS separately, system swap and
  pressure, installed RAM, stage, completeness, errors and timestamps. Unique
  per-command/per-attempt files and summaries live under each job's `memory/`;
  job status exposes their paths. Engine and settings provenance stays in the
  enclosing immutable plan. No GPU allocation fences or automatic profile update.
- Added functional tests for explicit refusal/override, unknown domains, invalid
  policy, nested-context restoration, native/MCP plan persistence, non-memory
  validation, queued dispatch, subprocess propagation, real Darwin readings and
  missing-counter handling. Added the suite to Tests/run.py.
- Recommended 1E3V → 1CTT → 13PK, followed by cross-chain 1DBT. Audited exact
  selected atom counts and retained source hashes/CCD audit status. Corrected
  collection count to 41. Earlier 1QFE pilot suggestion is superseded because its
  released DHS atom set mismatches the installed CCD. Wrote prospective budget,
  lab priorities, analogue-versus-substrate distinction and defer list in
  [MOTIF_BETA_PILOT](../docs/MOTIF_BETA_PILOT.md).

## Results

No model-memory calibration, inference throughput or enzyme measurements.

- 8 new override/telemetry tests passed, including a real inert child process
  with actual process supervision and memory counters; no models loaded.
- 27 admission tests passed; 25 native queue tests; 24 MCP tests; 6 plan reuse
  tests; 2 code snapshot tests; 1 motif bridge test.
- Swift build and local development app build/signature verification passed.
  Seven bundled memory-related code files matched source bytes.
- Installed runtime detection completed successfully. It does not qualify the
  new motif inference route or establish an engine-version performance result.
- `git diff --check` passed. Development app remains
  `build/iProteinStudio.app` (0.2.26, build 72), not installed or launched.
- Initial sandboxed native queue tests could not read macOS memory counters;
  the same suite passed with normal host counter access. The inert integration
  test initially had a string-versus-Path assertion error; corrected and rerun.

Logs, exact case selections, source hashes and bundle checks are retained in
[artifacts/0517-optional-memory-pilot](artifacts/0517-optional-memory-pilot/).

## Decision and rationale

An unavailable estimate must remain visible but need not prevent an explicitly
requested run. Keep enforcement as default; bind overrides into plans instead
of consulting mutable preferences at execution. Preserve the original rejection
so measurement records are useful and an override cannot be confused with a
qualified workload. Do not relax or fabricate memory profiles just to unblock
the pilot. New empirical limits still require a Validation campaign and audit.

The proposed three-case core spans a single organic ligand, ligand-plus-zinc,
and two organic ligands-plus-magnesium while retaining manageable motif sizes.
1DBT adds genuine cross-chain source mapping. This is a diagnostic panel, not a
representative estimate of AME success. KSI and cytidine deaminase have published
direct UV activity assays, but fixture ligands are analogues/inhibitors and do
not themselves establish catalytic activity. References are linked in the plan.

## Reproduce

From the canonical repository:

```bash
python3 Tests/test_memory_override.py
python3 Tests/test_memory_admission.py
python3 Tests/test_desktop_jobs.py
python3 Tests/test_mcp_bridge.py
python3 Tests/test_plan_reuse.py
python3 Tests/test_code_snapshot.py
python3 Tests/test_motif_beta_bridge.py
swift build
bash build_app.sh debug
```

Host process/memory counters are required for the inert process integration and
queue suites. No scientific GPU workload is invoked. Optional policies and
telemetry interpretation are documented in [MEMORY_SAFETY](../docs/MEMORY_SAFETY.md).

## Limits and what was not tested

No RFD3, MPNN or predictor inference, no experimental assay, no promoted memory
profile, no GPU-memory stress, no memory-exhaustion test, no automatic watchdog,
no installed application/runtime update, no launch/UI interaction test, no commit.
Existing unrelated changes were preserved. Only the new development build has
this UI/code; a connected older MCP server will not expose the new option.

Sampling can miss transient peaks. Process-tree sums can double-count shared
pages; accounted footprint is a memory ledger, not exact physical occupancy.
System swap/pressure includes other apps. Missing process readings remain null;
abrupt termination can leave partial logs. Counters from one small run cannot
justify unrestricted lengths, concurrency, ligands or hardware. The prospective
pilot still needs its Validation manifest, managed plan, raw outputs and audit.

## Next

Use the explicit override for one managed 1E3V root with both designers and
fixed-only sampling, guided proposals and untemplated checks. Inspect outputs
and memory before expanding to the proposed three-case comparison; qualify
Protenix/IntelliFold actual model execution separately from existing CPU feature
checks. Promote calibrated ranges only after bounded, audited measurements.
