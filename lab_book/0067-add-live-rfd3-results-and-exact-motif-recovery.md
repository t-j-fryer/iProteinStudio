---
entry: 0067
title: Add live RFdiffusion3 results and exact motif recovery
date: 2026-09-02
author: gpt-5-codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [rfd3, mlx, live-results, motif-scaffolding, partial-diffusion, validation]
---

## Context

Entry [[0066-add-rfd3-partial-motif-and-dual-validation]] added partial
diffusion and motif scaffolding, but RFdiffusion3 structures were still easiest
to inspect only after final ranking. The form also had no complete examples for
the new modes, and motif analysis needed to retain the identity of an unindexed
functional residue after it moved to a new scaffold position.

The first real multi-residue test exposed a more serious adapter defect. The
pinned Javier BQ MLX port represents side-chain atoms internally as generic
V-slots. Studio requested residue-specific atoms such as TRP NE1, but the old
output path retained only N/CA/C/O/CB and could silently discard the atoms that
defined the motif. Foundry's default unindexed mask also fixed more atoms than
the explicit request.

## What was done

- Added live RFdiffusion3 result discovery from append-only queue JSON/PDB
  checkpoints and successful verification CSV rows. Raw backbones are visible
  before MPNN or prediction completes.
- Added Overview, Structures and Hits sections to the persistent results sheet,
  automatic three-second refresh, metric-selectable score histograms, saved hit
  status and the existing py2Dmol structure controls.
- Replaced the original continuous-bin chart after a real 16-design manifest
  rendered it as apparently empty. The chart now follows a valid effective
  metric across live stage transitions, uses categorical histogram bins and
  always reports n, minimum, median and maximum below the plot.
- Added p53–MDM2 worked examples using bundled PDB 1YCR:
  - partial diffusion of the bound p53 chain at `partial_t=1.0 Å`, preserving
    its sequence and fixing the observed MDM2 structure;
  - a 70-residue scaffold around p53 F19, W23 and L26, with three explicit
    orientation-defining side-chain atoms per residue.
- Narrowed the MLX fixture's unindexed masks to only the requested generic atom
  slots, then translated every output slot back to the correct residue-specific
  atom name. A missing or inconsistent requested atom now fails loudly.
- Propagated strict-JSON `diffused_index_map`, `motif_fixed_atoms` and
  per-residue insertion diagnostics through generation, MPNN, ranking and the
  Swift results loader.
- Kept mapped motif identities fixed during MPNN.
- Added independent-prediction motif scoring. Each prediction is globally
  Kabsch-fitted on all explicitly constrained motif atoms; overall and
  per-source-residue RMSDs use that same fit. A requested motif filter fails if
  any atom or provenance is missing.
- Added an isolated validation harness that copies the app overlay, overlays its
  MLX sampler on the installed port, symlinks weights read-only and writes only
  below an ignored Validation output directory.

## Results

Both MLX runs used the app's exact final overlay, 200 diffusion steps, two
recycles, bfloat16, internal batch size one and seed base 17. These timings are
single-run smoke measurements, not throughput benchmarks.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| p53 partial diffusion, `partial_t=1.0 Å` | 1 | input→output binder Cα RMSD | 0.324 Å |
| same | 1 | adjacent binder Cα distances in 3.6–4.0 Å | 100% |
| same | 1 | full fixture + MLX stage wall time | 7.697 s |
| p53 F19/W23/L26 motif scaffold | 1 retained | requested atoms present in output | 9/9 |
| same | 1 retained | source→design constrained-atom RMSD after one global fit | 0.000000789 Å |
| same | 3 residues | per-residue RMSD under the same fit | 0.000000635–0.000000869 Å |
| same | 1 retained | adjacent binder Cα distances in 3.6–4.0 Å | 100% |
| same | 2 attempted | geometry rejection/resample before retained output | 1 |
| same | 1 retained | full fixture + MLX stage wall time | 33.804 s |
| SolubleMPNN handoff of motif output | 1 | mapped identities retained | F/W/L, 3/3 |
| SolubleMPNN handoff of motif output | 1 | sequences emitted / wall time | 1 / 1.37 s |
| Existing completed motif campaign | 16 structures | score-bearing structure paths found | 16/16 |

The generated motif row's `motif_insertion_rmsd=4.213 Å` describes the
pre-copy assignment of generated candidate slots to source motif tokens. It is
not the fixed-atom drift and is not the independent-prediction recovery score.
Those quantities are labelled separately to prevent a false pass or false fail.

Early disposable runs that accidentally symlinked the installed stale sampler
instead of overlaying Studio's `mlx_port/sampler.py` were excluded. They did not
test the app artifact and cannot support conclusions about partial diffusion.

## Decision and rationale

The app now treats RFdiffusion3 results as a live campaign rather than a final
report. Accepted structures are immutable checkpoints and therefore safe to
render immediately; hit labels remain absent until the configured verification
filters have actually been evaluated.

The p53–MDM2 motif is labelled a published binder-motif example, not a
MotifBench result. MotifBench primarily evaluates target-free monomer
scaffolding, whereas Studio's current workflow scaffolds a motif in the context
of a fixed binding target. Using 1YCR gives a compact, biologically interpretable
target-bound example without implying an unmeasured per-case RFD3 benchmark.

Exact atom provenance is a hard data contract. A structure containing the right
residue names but missing the selected functional atoms is not a successful
motif scaffold and may not enter ranking silently.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
~/.iproteinstudio/rfd3/.venv/bin/python Tests/test_rfd3_worked_examples.py
~/.iproteinstudio/rfd3/.venv/bin/python Tests/test_rfd3_motif_scoring.py

~/.iproteinstudio/rfd3/.venv/bin/python \
  Validation/experiments/rfd3_modes_smoke_v1/run.py \
  --output Validation/output/rfd3_partial_exact_overlay_defaults_20260902 \
  --mode partial --steps 200 --recycles 2

~/.iproteinstudio/rfd3/.venv/bin/python \
  Validation/experiments/rfd3_modes_smoke_v1/run.py \
  --output Validation/output/rfd3_motif_exact_overlay_defaults_20260902 \
  --mode motif --steps 200 --recycles 2

bash Tests/test_rfd3_results_ui_contract.sh
swift build --scratch-path /private/tmp/iproteinstudio-rfd3-live-build
```

## Limits and what was not tested

- Each real MLX mode has one retained backbone, on one M4 Max. This validates
  the execution, mapping and geometry contracts, not biological success rates.
- The new examples were not run end-to-end through every selectable complex and
  binder-alone predictor in this pass. Full Boltz, IntelliFold, OpenFold and
  Protenix verification remains a separate compute-heavy acceptance matrix.
- Independent-prediction motif scoring has synthetic regression coverage; a
  full p53 motif campaign has not yet supplied empirical distributions from
  which to calibrate the editable default 1.0 Å hit threshold.
- Target binding and experimental enrichment were not measured.
- No M1 run or release DMG was produced in this entry.

## Next

Run the two examples from a packaged build on M1 and M4, then perform a governed
multi-backbone motif campaign with at least two independent predictors. Retain
the unfiltered score distribution so experimental testing can calibrate, rather
than retrospectively justify, the motif and interface thresholds.
