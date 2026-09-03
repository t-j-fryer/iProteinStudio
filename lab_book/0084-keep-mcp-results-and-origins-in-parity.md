---
entry: 0084
title: Keep MCP result and surface-origin behavior in parity
date: 2026-09-03
author: gpt-5.6
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [mcp, agents, rfd3, results, iterative, release]
---

## Context

Entries `[[0082-nest-result-derivatives]]` and
`[[0083-play-iterative-cycle-trajectories]]` improved the native result model,
but MCP clients still received unrelated CSV tables. An agent could therefore
flatten one RFdiffusion3 backbone and its MPNN derivatives, treat complex and
binder-alone predictions as separate designs, or promote a whole parent because
one checked child passed. MCP already accepted the surface placement modes from
`[[0077-add-explicit-protein-surface-origin-modes]]`, but its result contract and
client guidance needed to be versioned with the new UI behavior.

## What was done

- Incremented the staged bridge to MCP v6 / server 1.1.0.
- Added read-only `results_overview` and a matching run resource. Iterative
  output is run → ordered cycle → design, independent complex and binder-alone
  artifacts. RFdiffusion3 output is generated MLX backbone → MPNN derivative →
  paired complex and binder-alone validation.
- Included iterative trajectory frame metadata using only design-stage cycles,
  with cycle 00 as the reference and the GUI's matching target-chain Cα
  alignment contract. Validation folds are explicitly excluded.
- Kept saved hit verdicts on checked cycles/derivatives and returned only
  verified run-relative artifact paths. Relocated campaign paths are recovered
  by suffix without exposing obsolete or arbitrary external absolute paths.
- Added completed iterative comparison tables to bounded `results_query`, while
  retaining the overview as the required first interpretation step.
- Strengthened MCP initialization instructions, `workflow_guide`, the RFD3
  schema, README, CLI documentation, AGENTS/Claude guidance and the shipped
  Claude skill. With no epitope, a protein de-novo plan resolves to
  `surface_scan`; target COM is rejected, broad patches stay non-hotspot
  positioning, and targeted epitopes remain explicit hotspot conditioning.
- Added executable bridge tests for both hierarchies, child verdicts, binder-only
  score semantics, raw iterative distributions and tool/profile exposure.

## Results

No model inference or performance measurement was run; this was orchestration,
result interpretation and release integration.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| MCP bridge suite | 15 tests | pass | 15/15 |
| Managed RFD3 surface-origin suite | 4 tests | pass | 4/4 |
| Real managed RFD3 result overview | 5 backbones / 10 derivatives | recovered hierarchy | 5 / 10 |
| Supplied iterative campaign result contract | 12 runs / 72 cycles | grouped trajectories | 12 / 12 |
| Real WebKit trajectory check | 2 cycle CIFs | load and target alignment | pass |

## Decision and rationale

The bridge now exposes a semantic overview rather than asking language models to
reconstruct parentage from overloaded names. Raw `results_query` remains because
agents still need exact saved columns and distributions, but it follows the
overview. This avoids duplicating scientific ranking logic: the runner's saved
verdict remains authoritative.

No-epitope RFD3 design is represented as an explicit surface-scan mode, not an
empty origin field. That makes the safe behavior visible in the immutable plan
and prevents different clients from inventing COM, hotspot, or single-origin
fallbacks.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

/usr/bin/python3 Tests/test_mcp_bridge.py
/Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python \
  Tests/test_rfd3_surface_origins.py -v
bash Tests/test_iterative_results_ui_contract.sh
bash Tests/test_rfd3_results_ui_contract.sh

/tmp/iproteinstudio-results-contract iterative \
  /Users/thomasfryer/Downloads/untitled_prediction_2
/tmp/iproteinstudio-results-contract \
  /Users/thomasfryer/.iproteinstudio/projects/untitled_design/rfd3_runs/acbx_1ctx_surface_ema_smoke5
/tmp/iproteinstudio-py2dmol-trajectory \
  Sources/iProteinStudio/Resources/web/py2dmol/viewer.html \
  /Users/thomasfryer/Downloads/untitled_prediction_2/run_001/cycle_00/pred_min/model_0.cif \
  /Users/thomasfryer/Downloads/untitled_prediction_2/run_001/cycle_01/pred_min/model_0.cif
```

## Limits and what was not tested

No new protein design, MPNN or structure-prediction inference was necessary
because MCP calls the already validated managed runners without changing their
scientific arguments. Synthetic bridge fixtures exercised both result layouts;
the new RFD3 overview was additionally read against a real five-backbone run.
The iterative hierarchy and WebKit trajectory used the supplied moved campaign,
which is outside managed MCP storage, so its MCP path guard was exercised with
synthetic relocated paths instead. Remote transport was tested on loopback; no
public HTTPS tunnel or phone client was configured. The M1 GUI remains a manual
cross-machine display check.

## Next

Use a fresh Codex or Claude Desktop chat to call `workflow_guide`, create a
one-backbone no-epitope plan, inspect its normalized `surface_scan` request, and
then inspect the completed derivative with `results_overview` before any raw
score query.
