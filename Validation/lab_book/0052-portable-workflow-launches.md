---
entry: 0052
title: Qualify portable engines through public workflows
date: 2026-09-26
author: Codex
type: experiment
status: complete
machine: Apple M4 Max, 64 GiB unified memory, macOS 26.6.1
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

## Pause checkpoint

Biotin job `job-221c7d6db092` stopped through the broker; state cancelled,
no error, execution lease free. 10,403 existing completion receipts hashed
before stopping. Same plan/digest must be resumed after installed acceptance.
Engine detection reports all supported components installed.

## Limits

The final launch outcome is recorded below.
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

## Launch outcome

The final matrix has 23 current cases: 21 completed, with Boltz and PSICHIC NISE
scoring followed by the unchanged zero-survivor structural gate in the other two.
All 23 output audits pass within that declared launch scope. NESSO completed an
optimization cycle. The repaired constrained-Protenix case completed through the
normal portable installer. All 39 attempts are retained, including original
software failures.

Additional defects fixed: portable activation, redundant Boltz extra verifier,
OpenFold mixed-MSA input, orderly child shutdown, RFdiffusion3 ligand atom export,
installer process classification, and a missing constrained-Protenix receipt
marker. The paired export fix leaves all 44 model input arrays and 276 output atom
coordinates unchanged. See [project Lab Book 0199](../../lab_book/0199-qualify-portable-workflow-launches.md)
for individual failures, executable regressions, runtime identity, publication
and production-resume receipts. Public evidence:
[launch-evidence.json](../../lab_book/artifacts/0199-workflow-launches/launch-evidence.json).

This is one-Mac integration acceptance. Fresh-Mac installation, other chips, large
inputs, memory soak and experimental design quality were not qualified. OpenFold
random-binder geometry warnings are retained rather than hidden.

App0.2.8/build54/MCP29 is published, downloaded/verified and installed. The same
production biotin job resumed at cycle7: two new completion receipts were observed
with all 10,403 old receipt hashes unchanged. Publication and resume evidence are
linked in project0199. The campaign was left running.
