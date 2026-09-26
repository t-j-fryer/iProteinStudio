---
entry: 0199
title: Qualify real engine launches before release and resume biotin
date: 2026-09-26
author: Codex
type: experiment
status: in-progress
machine: Local Apple Silicon Mac; exact hardware captured in campaign manifest
---

## Context

User requested safely stopping the current biotin campaign, testing every
compatible engine through Protein Hunter, RFdiffusion3, NISE and Predict,
fixing failures, publishing/updating the app and MCP, then resuming biotin.
This follows portable activation defect 0198. No model-performance claim.

## Protocol

Harness/configuration: `Validation/experiments/portable_workflow_launch_v1/`.
Raw outputs/receipts: `Validation/output/portable_workflow_launch_v1/`.
Use managed plans, immutable digests and the shared execution lease for GPU work.
Small output budgets, unchanged engine diffusion/recycle/precision defaults.
Review result overviews and audit structure cardinality, sequences, finite
coordinates and confidence files. Preserve failed attempts. No student-target
rerun or high-budget new campaign. Never mutate retained biotin code/settings.

## Status

Biotin job `job-221c7d6db092` stopped through the broker; state cancelled,
no error, execution lease free. 10,403 existing completion receipts hashed
before stopping. Same plan/digest must be resumed after installed acceptance.
Engine detection reports all supported components installed.

## Limits

In progress. No broad success claim until the declared coverage matrix passes.
Fresh-Mac/cross-chip performance and long-run science acceptance are separate.

## Additional integration defect found

The first real small-molecule RFdiffusion3 case completed backbone generation,
LigandMPNN, and primary Boltz inference, then failed with `Unsupported predictor(s):
boltz`. Its public MCP request had included Boltz in `extra_predictors`, which the
schema and preparer accepted, but the ligand second-opinion adapter rejects.
Native Studio already removes this redundant primary engine. Match that behavior
in MCP normalization and direct/saved request preparation; retain independent
extras and the mandatory primary Boltz/affinity work. Preserve the failed case
`rfd3-ligand`; queue a fresh `rfd3-ligand-retry` through source MCP29 with the same
scientific request. No component package or frozen failed plan was modified.

Regression: MCP bridge 19 tests and workflow pipeline contracts pass. The latter
also exposed a stale test hardcoding the former IntelliFold PyTorch2.6 pin; it now
checks the launcher against the installed-version lockfile (currently2.14).
All58 fast-suite commands passed, including ten sandbox-blocked checks rerun with
normal process/local-network/compiler access. `swift build` passed in the main
and isolated release worktrees. No throughput claim.

## Further integration findings

- OpenFold's explicit-empty binder plus cached target MSA request failed inside
  upstream `create_main`: its auto-generated NPZ is keyed `dummy`, absent from
  the configured source order. The shared query adapter now materializes the
  requested single query as `colabfold_main.a3m` only in mixed-MSA requests.
  Target alignment bytes remain unchanged; all-empty inference still disables
  MSAs; no server fallback is introduced. Workflow executable regression passes.
- The broker previously treated every surviving child immediately after parent
  exit as an orphan. It now retains the execution lease for two seconds of
  orderly shutdown, then preserves owned-process evidence and performs the
  existing termination/escalation. Actual prediction errors survive cleanup.
  All22 broker tests pass, including real detached child shutdown, orphan
  termination, cancellation/queueing, and failure-message preservation.
- RFdiffusion3 feature names intentionally anonymize atomized ligand atoms to
  element symbols. The MLX PDB writer incorrectly reused these as identifiers,
  yielding repeated C/O names and failing NISE's strict ligand handoff audit.
  Feature capture now stores original atom names and elements as separate export
  metadata. The writer validates cardinality, uniqueness and element order, and
  changes only exported names/elements. Model feature arrays and coordinates are
  not edited. Old ambiguous ligand fixtures fail with a regeneration instruction.
  Three writer regressions and18 RFdiffusion3 audit regressions pass.

Derived a new portable RFD3 package from the installed verified closure, changing
only `milestone0_oracle.py` and `scripts/generate_backbones.py`;36,894 inventoried
files are unchanged. New identity:
`c9fc19327d6b15b5a14b83b3d99c914e1dc52d2b2d1eb9e87b6cf0be49d27a3a`.
Archive396,215,713 bytes, SHA256
`a626ce5ab19bca66b25f128935db64387a9621602654f17517c8d92d900a9ea8`.
No weights included. Inventory verification and relocation imports pass; the
sandboxed import emitted a Metal-at-exit diagnostic, so GPU qualification relies
on the subsequent normal-session managed activation and real jobs, not that import.
Transactional activation retains the old runtime and every existing binding.

Queued acceptance attempts were cancelled before execution to permit safe
staging under registry/execution/install locks. Fresh `*-fixed` plans preserve
those attempts and use the new code/runtime; no frozen plan was patched.
The single-start Boltz NISE attempt reached the Phase0 cycle02 structural gate
and had no survivor. Retain this as a scientific rejection, not a launcher defect.
A three-start diagnostic attempt exercises downstream work without weakening
geometry gates. No proposed scientific default or speed claim.

The broader science-fixture suite passed17/19 initially. Two test-environment
issues were isolated: objective test lacked its own NANOHUNTER_ROOT setup, and
RFD3/NISE ligand tests require Boltz imports absent from the Protenix test Python.
The objective test now declares its source root; both files pass (three tests
each) under the installed Boltz/RDKit Python. No model inference in these tests.
