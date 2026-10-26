---
entry: 0491
title: Preserve original motif correspondence
date: 2026-10-21
author: Codex
type: implementation
status: complete
machine: Local Apple Silicon Mac; native CPU preprocessing and development build only
tags: [rfd3, motifs, protenix, intellifold, templates, scoring, beta]
---

## Context

Following [[0490-support-original-motif-residue-templates]], the user requested
native Protenix/IntelliFold checks, initial backbone ranking against the original
motif, and persistent motif positions for scoring every subsequent prediction.
Recovery of a generated backbone is not necessarily recovery of the original
active site. The RFD3 writer also copies selected fixed atoms into the exported
PDB, which can conceal differences among pre-export scaffold proposals.

## What was done

- Executed installed Protenix 2.0.0 and IntelliFold 2.0.4 native template parsers
  and dense/model feature builders on all 41 released motif fixtures. Used
  explicit, deliberately reordered query positions in repeated sequences.
  Protenix used Studio YAML conversion and native JSON correspondence;
  IntelliFold used its Studio local-template whitelist, native A3M parser and
  native featurizer. No model weights were loaded.
- Verified exactly the requested observed positions and backbone-frame masks.
  Moving distal sidechains by 3 Å changed raw atom arrays but did not change
  pseudo-Cβ distograms, backbone masks or frame vectors in either engine.
  Sparse complete residues work as template inputs; sidechain coordinates do
  not become hard atomic constraints. Tip-only theozymes lack these frames.
- Added source residue → query chain/1-based position/identity/atom-mask records
  to frozen beta references and scoring reports. All selected atoms use one
  global alignment to original input; per-residue errors retain that same fit.
  Added CPU `score-input-motif` for compatible structures from any predictor,
  including apo structures. Missing or changed identities/atoms fail.
- Versioned beta ranking to `studio-ame-beta-v2`: original-input selected-atom
  RMSD now drives greedy/beam ranking alongside the existing worst ligand
  centroid term. Root-relative all-heavy motif RMSD and computational passing
  metrics remain separate. Old bundles must be regenerated.
- Added original coordinates, mapping/atom-mask checksums and pre-copy global
  motif RMSD to new RFD3 unindexed-motif generation metadata; retained these
  through sequence design and selection. Beta root manifests rank by pre-copy
  RMSD, then exported RMSD, retaining all requested roots. New validation rows
  score original input separately from generated-backbone recovery. Original
  provenance missing in legacy rows is unavailable, never reconstructed from
  a generated backbone. New original-reference rows receive the motif gate on
  original recovery as well. General ligand analysis exposes the input metric.
- Added distinct Studio results metrics and reference-aware per-residue labels;
  MCP results preserve the new fields. Updated overlay checksum and beta docs.

## Results

No inference, assay or performance measurements — implementation and CPU checks.

| Check | Result |
|---|---|
| Native Protenix sparse features | 41/41 cases; 2 tests passed |
| Native IntelliFold sparse features | 41/41 cases; 2 tests passed |
| Beta geometry, mapping, ranking and fake orchestration | 16 tests passed |
| Native Boltz parsing and ligand chemistry | 5 tests passed |
| RFD3 export, including pre-copy distortion | 5 tests passed |
| Original-input scoring and gate integration | executable regression passed |
| RFD3 audit/checkpoint regressions | 18 tests passed |
| Immutable managed preparation plan | 1 test passed |
| Executable Swift results contract | passed |
| Swift build and local app build/signature | passed |
| Bundled motif/overlay Python bytes | 43 files matched source |
| Whitespace patch check | passed |

Logs, per-case positions, installed native source hashes and build verification:
[artifacts/0491-motif-correspondence](artifacts/0491-motif-correspondence/).
App: `build/iProteinStudio.app`, version 0.2.26 (72), not installed or launched.
Initial IntelliFold sandbox cache failure was resolved with a task-local Numba
cache; no runtime installation changes. Final successful logs are retained.

## Decision and rationale

Use the original selected atoms as the immutable objective; using a moving
root reference could reward retaining an initial error. Keep generated-backbone
recovery as a distinct fold diagnostic. Rank initial proposals before fixed
atoms are copied: exported exact matches alone cannot distinguish placements.
One global motif fit measures arrangement; separate residue fits would hide it.
Ligand centroids/pose diagnostics still use the root pocket frame and remain
separate from the original motif fit. This is a beta objective, not an exact
Artios benchmark reproduction or a catalytic-activity metric.

Complete native residues can guide the predictors without an intervening
backbone, once their positions in a full query sequence are specified. For an
atomic-only theozyme, RFD3-generated residue frames provide a practical guide;
the theozyme's original atomic coordinates must remain the scoring reference.

## Reproduce

From the canonical Studio repository, use the installed engine interpreters:

```bash
MPLCONFIGDIR=/tmp/motif-beta-mpl MOTIF_FEATURE_ENGINE=protenix-v2 \
  "$NANOHUNTER_ROOT/venvs/NanoHunter_protenix/bin/python" Tests/test_motif_template_features.py
MPLCONFIGDIR=/tmp/motif-beta-mpl NUMBA_CACHE_DIR=/tmp/motif-beta-numba \
  MOTIF_FEATURE_ENGINE=intellifold \
  "$NANOHUNTER_ROOT/venvs/NanoHunter_intellifold/bin/python" Tests/test_motif_template_features.py
MPLCONFIGDIR=/tmp/motif-beta-mpl \
  "$NANOHUNTER_ROOT/venvs/NanoHunter_protenix/bin/python" Tests/test_motif_beta.py
python3 Tests/test_motif_beta_bridge.py
swift build
bash build_app.sh debug
```

The RFD3 export/scoring/audit tests use a Python environment with NumPy; the
Boltz native test uses its installed environment. Optional
`MOTIF_FEATURE_AUDIT=path.json` records per-case native feature positions.
The Swift executable contract is `Tests/PredictionResultsContractHarness.swift`
with RunResult, RunResultsLoader, NISEResults and ControlPython sources, as
specified in `Tests/run_swift_contracts.py`.

## Limits and what was not tested

The existing memory-admission policy still blocks real RFD3, ligand-complex and
guided beta inference. No bypass, model execution, weights changes, installed
runtime modification, scientific campaign, laboratory experiment or throughput
measurement. Only Boltz is wired into beta automatic cycles; Protenix and
IntelliFold exports are CPU-feature-qualified, not model/cycle-qualified.
No inference robustness conclusion follows from successful input preprocessing.

Original-reference metadata is implemented for new RFD3 unindexed-motif outputs
and the beta frozen-reference contract. This does not add arbitrary motif
GUI authoring, migrate every legacy workflow, or imply atomic restraint support
in unrelated engines. Future motif adapters must supply the same explicit
mapping/reference contract; correspondence must never be guessed by residue
number. Symmetric atom names, low-atom ligand-anchored fits, ligand chemistry
variants, clash/angle filters and exact Artios-38 membership remain unresolved
as described in the earlier entries. No commit made; unrelated work preserved.

## Next

Qualify memory profiles and a managed one-root end-to-end smoke run with both
sequence designers, original versus generated residue guides, untemplated
ranking, and an independent predictor-family assessment. Qualify native
Protenix/IntelliFold model execution before enabling their automatic cycles.
