---
entry: 0207
title: Publish Protein Hunter predictions before a cycle finishes
date: 2026-09-28
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 64 GB unified memory; model-free tests only
tags: [predictors, ui, resume]
---

## Context

Following 0206, the user requested immediate structure visibility instead of
waiting for the full Boltz cycle, and ten trajectories when selecting examples.

## What was done

Added a request-scoped Boltz writer wrapper in live_iterative_results.py. After
the native writer returns successfully, the helper verifies saved input identity,
structure readability and confidence JSON, then atomically publishes a relative-
path live_prediction.csv under the exact run/cycle. Model, RNG, cycle scheduling,
sequence design and scientific resume checkpoints are unchanged. Only new
iterative Boltz requests opt in; NISE and Predict requests do not.

Swift result loading, the Overview metrics watcher and MCP merge individual
receipts with completed-cycle metrics, preferring completed-cycle rows. Failed
or unfinished predictions never publish. Restarted pending inputs clear previous
display receipts before overwriting their raw outputs. Successful siblings remain
browseable after a later prediction failure. Boltz now emits per-request completed
counts through the existing resident progress channel.

Protein Hunter ExampleTarget.apply sets numDesigns=10. Ordinary defaults, saved
requests and RFD3 examples remain unchanged. Documented the new behavior in CLI.md.

## Results

No performance measurements or inference-quality claims. Swift build passed.
Five executable writer/session publication tests passed, including a failure on
the second prediction after the first was published. Three MCP combined-results
tests passed. Swift result and iterative command/metrics harnesses passed, as did
the iterative UI contract. Existing resident resume suite: 13 passed, one skipped
because the actual Accelerate CPU-loader fixture needs the IntelliFold environment.
The suite's first run exposed a shell fixture's unset optional binder-chain value;
the request builder now uses the established A default when absent, and the suite
passes. A duplicate local name in the Swift fixture was also fixed before rerun.

## Decision and rationale

Use atomic display-only receipts rather than treating raw file existence as
completion or altering scientific resume state. Completed-cycle metrics remain
the canonical final representation. Preserve earlier completed predictions after
failure rather than hiding an entire failed wave.

## Reproduce

Run Tests/test_live_iterative_results.py with managed Boltz Python (PyYAML),
Tests/test_framework_batch_results.py, Tests/test_resident_prediction_resume.py,
the results and iterative cases from Tests/run_swift_contracts.py, and
bash Tests/test_iterative_results_ui_contract.sh. Run swift build.

## Limits and what was not tested

No new GPU inference, biological validation, end-to-end scientific campaign,
fresh-Mac installation, or timing benchmark. No changes to the ongoing NISE run
or its retained snapshot. Incremental publication is currently for resident
Boltz Protein Hunter; other engine schedulers retain previous behavior. Installed
and published release builds are not modified by source changes alone.

## Next

Include in the next distributed app and MCP deployment. Older frozen campaigns
require their original code; this feature applies to new snapshots.


## Local app artifact

Debug and release builds passed. Packaged a separate ad-hoc-signed development
app at build/live-results/iProteinStudio.app using the existing packaging script
with only its output location changed. Deep strict code-signature verification
passed; the live-results helper, resident runner, shell, MCP catalog and provenance
file hashes match source. The existing open app was not replaced, no public
release was published, and no campaign processes were restarted. This local
preview retains version0.2.9/build55 and has self-updates disabled; it is not a
new distributed release. No interactive UI launch test was performed.
