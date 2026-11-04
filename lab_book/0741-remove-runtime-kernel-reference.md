---
entry: 0741
title: Remove automatic RFD4 kernel reference runs
date: 2026-11-04
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

## Context
User approved moving expensive standard/optimized equivalence comparisons into
developer validation. The pinned model, kernel and PyTorch release are maintained
by Studio. Repeating reference inference in each production job adds overhead.

## What was done
Removed reference generation and per-input qualification from the shared RFD4
stage runner used by app, CLI and MCP. Every requested family invokes its selected
kernel path once; completed family receipts remain reusable. The optimized flag
and default remain unchanged. Model operations, weights, sampling schedule,
finite-output, target sequence, cardinality and completion-digest checks are intact.
UI, MCP workflow guidance and RFD4 documentation describe the new behavior.
Build80/MCP53 identifies the updated package. Existing frozen plans retain their
original code and behavior; no active job or installed model runtime was modified.
Matched standard/optimized developer validation remains available; no new public
request flag or schema migration is needed.

## Results
Executed regression tests exercise the actual generation-stage loop with a fake
model: standard/optimized call counts, distinct family inputs, initial smoke then
expansion, no-work resume, and tampered-artifact rejection. Three tests passed.
MCP bridge24 tests and sealed-bundle entry-point test passed. Swift builds and
beta/public build80 packaging passed, including code-signature checks. Packaged
generation hashes match source; packaged CLI doctor reports MCP53 and guide
returns the new policy. All53 RFD4 tests passed in the configured runtime, including native CPU input
authoring and adapters. No new speed measurements.

Initial broad runs lacked biotite (system Python), then runtime/tool import
configuration. The fully configured rerun uses the installed RFD4 Python,
NANOHUNTER_ROOT and PYTHONPATH=tools. These setup failures are retained in logs.
The packaged CLI guide needed normal audit-log permissions and then passed.

## Decision and rationale
Remove automatic reference inference rather than caching qualification by target:
target identity is not an appropriate reason to duplicate the model call. Keep
numerical equivalence in developer validation and inexpensive output checks in
normal execution. This change does not enable optimized kernels by default.

## Reproduce
`python3 -B -m unittest discover -s Tests -p 'test_rfd4*.py'`
`swift build`; `bash release/build_local_beta.sh` (private beta), or
`bash build_app.sh debug` (public candidate).

## Limits and what was not tested
No new GPU run or additional hardware qualification. Inference operations are
unchanged; tests qualify removal of redundant scheduling. Existing jobs remain
frozen. Installed shared CLI/MCP staging and public binary publication are separate
from building this candidate; the earlier release acceptance hold remains.
