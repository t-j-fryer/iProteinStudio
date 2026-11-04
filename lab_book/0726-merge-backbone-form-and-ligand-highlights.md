---
entry: 0726
title: Merge backbone configuration and show ligand atom conditions
date: 2026-11-03
author: Codex
type: bugfix
status: complete
machine: Apple Silicon development host; no performance measurements
tags: [rfd3, rfd4, ui, ligand, public-candidate]
---

## Context

Follow-up to 0719. The user correctly rejected a segmented generator switch
between two complete screens as insufficient integration. They requested one
form, clear molecule-action explanations, easy clearing and visible atom roles,
and asked whether RFD4 requires tautomer handling.

## What was done

- One scroll container, shared heading, in-form generator menu and shared setup
  detail selector. RFD3 and RFD4 now supply configuration fields rather than
  separate tab screens. De novo SMILES inputs, linker endpoints, conformer
  choices and canonical atom conditions carry across generator switches.
  Model-specific settings and native translation remain separate internally.
- Explained Analyse (chemistry checks, conformers, optional PDB lookup), Inspect
  (atom identity/roles) and suggestions (review then apply; no guessed hotspots).
  RFD4 suggestions now require review before replacing conditions. Linker-aware
  suggestions require completed linker analysis. Clearing invalidates previews.
- Shared Clear all atom conditions plus five coloured roles and B/E/D/A/H labels.
  Split rings show simultaneous roles, including donor and acceptor on one atom.
- Visual QA exposed an existing offset from estimating atom positions using split
  bond paths. The renderer now reads exact centres from RDKit's own highlight
  ellipses in the displayed SVG; missing centres fail instead of guessing.
- Tautomer notes moved into an optional disclosure. The text distinguishes
  chemical state from 3D conformers and explains that enumeration is not a
  population estimate at assay pH. Supplied SMILES chemistry is unchanged.
- Applied only the incremental task patch to the existing local public candidate,
  preserving its public baseline and excluding private beta differences.

## Results

No measurements — UI implementation and verification only; no scientific models
or GPU campaign were run.

- Native WebKit harness passed original None/Bind/Expose controls and the new
  five-role rendering, simultaneous roles, letter labels, resize retention,
  exact carbon bond-endpoint alignment, and host-driven clearing checks.
- Inspected the renderer screenshot; all roles were visible at atom centres.
- Swift build passed. Both existing beta and public candidate packaging scripts
  completed and verified ad-hoc signatures (0.2.31-dev / 0.2.31, build 77).
- Live UI check used a temporary copy with a distinct bundle ID, since the user's
  already-running beta retained the older executable. Verified one generator
  dropdown/form and SMILES preservation across RFD4 to RFD3. Existing draft was
  restored after inspection; no jobs were submitted or active outputs modified.
- Source whitespace checks passed. Packaged resource hashes checked against
  their respective source trees. Evidence is in
  `lab_book/artifacts/0726-backbone-form/`.

## Decision and rationale

Tautomer enumeration is an optional chemistry note, not an obligatory RFD4 step.
Checked the official paper (116 pages; extracted using PDFKit), pinned upstream
source and current upstream benchmark README on 2026-11-03:

- Paper Section S7.1.3, page 65, assigns donor/acceptor roles with RDKit Lipinski
  patterns on a pH 7.4-protonated ligand copy for its interaction-search experiment.
  A case-insensitive search of the extracted paper found no `tautomer` occurrence.
  This supports the narrower statement that the inspected paper does not describe
  routine tautomer enumeration, not that chemical-state choice is irrelevant.
- Pinned `configs/metrics/inline_metrics/ipa_metrics.yaml` has `tautomerise: false`.
- Upstream DISCO Figure 2C input README explicitly discusses a uric-acid bond-order
  issue that is not an equivalent tautomer and cautions that protonation/metal
  conventions can vary. Chemistry identity remains important.

Sources: [official paper](https://rfd4-proteina.org/assets/paper/RFD4-Proteina.pdf),
[interaction metric settings](https://github.com/RosettaCommons/RFD4-Proteina/blob/main/configs/metrics/inline_metrics/ipa_metrics.yaml),
[benchmark chemistry caveats](https://github.com/RosettaCommons/RFD4-Proteina/blob/main/data/benchmarks/small_molecule_binder/disco_figure_2c/README.md).

## Reproduce

```sh
CLANG_MODULE_CACHE_PATH=/tmp/studio-clang-cache STUDIO_ATOM_SCREENSHOT=/tmp/studio-atom-conditions.png bash Tests/test_ligand_atom_selection.sh
CLANG_MODULE_CACHE_PATH=/tmp/studio-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/studio-swift-cache swift build --disable-sandbox
bash release/build_local_beta.sh
# In .worktrees/paper-release:
bash build_app.sh debug
```

WebKit UI verification requires desktop access. An earlier concurrent harness
compile was interrupted by editing its source; the final serial invocation above
passed. The initial paper text-extraction attempt lacked pdftotext; PDFKit text
extraction completed with host access. No dependency or model runtime was changed.

## Limits and what was not tested

No inference, efficacy, pH/population prediction or new tautomer pipeline was
qualified. Diagram interaction/geometry used ethanol; exhaustive dense-molecule
layout testing was not done. No live PDB query was submitted. Backend scientific
contracts are unchanged from 0719, whose new GPU combinations remain pending
qualification. The public app remains a local candidate, not a published release.

## Next

Reopen the rebuilt beta to load the new interface. Continue the previously
recorded GPU qualification separately before promoting the candidate.
