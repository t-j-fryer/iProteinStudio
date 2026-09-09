---
entry: 0112
title: Audit inactive nanobody and beta settings in a minibinder manifest
date: 2026-09-08
author: Codex
type: audit
status: complete
machine: Local macOS developer machine; read-only campaign inspection
tags: [predictors, ui, provenance]
---

## Context

The user queried scaffold, CDR3 and beta fields in the completed
`untitled_design_boltz_6ed978fa/studio_run.json` under the managed runtime's
`projects/untitled_design` directory. The intended workflow was minibinder.

## What was done

Read the saved manifest, actual prediction YAML, all trajectory secondary
structure plans and CDR mask files, all MPNN logs, and the campaign-owned frozen
pipeline. Traced current native `DesignRequest`, `TemplateWriter`,
`CommandBuilder`, `RunController` and `StudioRunManifest` serialization.
Only this entry and its index were written; historical run files were preserved.

## Results

No performance measurements — provenance audit only.

- Saved request says `designType: minibinder`. Recorded launch explicitly uses
  `--workflow protein --random-binder`, Boltz and SolubleMPNN. Scaffold and CDR
  arguments are absent. Actual initial chain A is a generated masked sequence;
  the template's poly-G placeholder is replaced before prediction.
- All 50 trajectory plans have unconstrained positions, no beta blocks,
  `mode: antihelix`, `anti_helix_strength: 0.0`, and `seed-only` scope.
- All 100 nanobody-named position/mask files are empty. The generic protein
  cycle-wave initializer deliberately creates these empty shared-state files.
- All 250 MPNN logs list every residue of chain A as redesigned, matching each
  trajectory's full length. No position-specific secondary-structure bias files
  were found in those MPNN directories.
- The frozen runner sets the internal antihelix mode when the explicit
  `--negative-helix-constant 0.00` flag is provided, including at zero strength.
  Its seed helper applies neutral helix multipliers at zero and enables beta/
  turn weights only for beta or mixed mode. Thus the stored beta strengths of
  0.5 have no effect here. Seed-only scope excludes later MPNN bias maps.
- The manifest embeds the entire shared `DesignRequest`, including inactive
  nanobody settings and retained legacy beta settings. This explains the
  vobarilizumab scaffold, CDR3 selection and stale seed-and-cycles UI value;
  these are not the effective execution configuration for this campaign.

## Decision and rationale

This was a minibinder run with no scaffold/CDR restriction or active secondary
structure bias. Preserve the original provenance rather than removing fields
from a completed run. A future presentation change should distinguish saved
form state from effective settings without discarding restoration information.

## Reproduce

Inspect `studio_run.json`, `inputs/design.yaml`,
`run_*/cycle_00/run_*_cycle_00.yaml`, `run_*/secondary_structure_plan.json`,
`run_*/nanobody*.txt`, and `run_*/cycle_*/ligandmpnn/ligandmpnn.log` in that
campaign. Compare with its `.studio_runtime/pipeline/nanohunter_run.sh`
(`initialize_cycle_wave_designs`, secondary-mode normalization and MPNN bias
scope guard) and `scripts/secondary_structure_control.py` (seed mode gating).

## Limits and what was not tested

No predictions, redesigns, benchmarks, GUI checks or builds were run. This audit
does not validate biological binding or independent prediction quality. Findings
apply to the saved campaign and its frozen code, not every historical run.

## Next

Consider labelling inactive/restoration-only fields explicitly in run metadata.
