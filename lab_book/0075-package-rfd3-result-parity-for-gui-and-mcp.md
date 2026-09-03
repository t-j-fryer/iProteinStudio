---
entry: 0075
title: Package RFdiffusion3 result parity for GUI and MCP
date: 2026-09-03
author: gpt-5.6-sol
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [rfd3, results, mcp, packaging, provenance]
---

## Context

Entry [[0074-make-rfd3-results-complete-and-movable]] compiled the shared GUI
result browser but did not assemble a refreshed application bundle. Its Swift
loader fix also did not by itself change the separate Python MCP catalog. The
MCP read profile could query a subset of CSVs, while the run profile that starts
scientific work could not list runs or query their results.

## What was done

- Extended the MCP result catalog to include RFdiffusion3 backbone metrics,
  design metrics, MPNN sequences and every supported complex/binder-alone
  prediction directory, including `monomer`.
- Added bounded backward-compatible `predictor` and `prediction_context` labels
  for older Studio-generated rows. New pipeline rows continue to persist those
  fields directly.
- Made the run MCP profile a superset of the read profile so one conversation can
  detect engines, plan/start work, inspect status and query results.
- Incremented the packaged bridge contract to MCP version 4 and documented the
  result behavior.
- Assembled and ad-hoc signed `build/iProteinStudio.app` with the GUI fixes and
  MCP v4 resources.

## Results

No new scientific inference or performance benchmark was run.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| MCP bridge integration suite | 13 | tests passed | 13/13 |
| Existing fluorescein campaign | 4 | result layers queried with provenance | 4/4 |
| Packaged app | 1 | deep signature verification | pass |
| Packaged run-profile MCP | 5 | required result/workflow tools present | 5/5 |
| Packaged app | 1 | size on disk | 33 MB |

The existing campaign returned `rfd3-mlx/generated_backbone` for backbone
metrics, `boltz/complex` for ranked and holo rows, and
`boltz/binder_alone` for apo rows. This validates compatibility against a real
pre-provenance campaign rather than only a new fixture.

## Decision and rationale

The MCP catalog remains an independent, read-only interpretation layer instead
of importing Swift UI code. This keeps the client-neutral server usable from
Codex and Claude without launching the app. Compatibility inference is limited
to Studio-owned dataset paths and known predictor output names; arbitrary rows
are not assigned a guessed engine.

The run profile inherits read tools because starting a job without being able to
inspect its managed results is an incomplete least-privilege workflow. The admin
profile remains separate.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

python3 Tests/test_mcp_bridge.py
bash Tests/test_rfd3_results_ui_contract.sh
python3 -m unittest Tests/test_rfd3_predictor_scheduling.py
~/.iproteinstudio/rfd3/.venv/bin/python Tests/test_workflow_pipelines.py

./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
cat build/iProteinStudio.app/Contents/Resources/iProteinStudioResources/pipeline/mcp/MCP_VERSION
```

## Limits and what was not tested

- The app bundle was assembled and signature/resource checked, but not launched
  or driven with GUI automation. There is still no multi-window macOS UI-test
  target.
- The bundle is an ad-hoc-signed development build, not a notarized public
  release and not a DMG. It was not copied over an installed application.
- The currently configured Codex/Claude commands still target the staged MCP v2
  under `~/.iproteinstudio`. Opening the rebuilt bundle atomically stages MCP v4;
  the AI clients must then be restarted so their MCP subprocesses reload it.
- No fresh heavy RFdiffusion3, complex-prediction or binder-alone prediction was
  run. Scientific execution coverage remains as recorded in Entries 0066–0074.
- The remote MCP gateway passed its authenticated loopback integration test, but
  no public HTTPS relay or phone client was involved.

## Next

Launch the built bundle, exercise Browse Live Results during a one-backbone
campaign, and test the same run from a fresh Codex or Claude conversation using
only the run-profile MCP tools.
