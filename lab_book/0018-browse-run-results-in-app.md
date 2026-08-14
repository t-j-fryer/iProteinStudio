---
entry: 0018
title: Browse prediction and design results in the app
date: 2026-08-14
author: codex-gpt-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, prediction, rfd3, results, metrics, structure]
---

## Context

Studio already bundled an offline 3Dmol viewer, but only the live iterative-design
dashboard and its individual tiles used it. A finished Predict batch offered only
`Show results` in Finder, old campaigns in Activity offered only a folder icon,
and RFdiffusion3 stopped at a small textual ranking summary. That made successful
science feel like a filesystem export rather than an app result.

The requested confidence summaries also need careful naming. AlphaFold 3's
`chain_pair_pae_min` is the minimum PAE across a pair of chains. Boltz's
`complex_ipde` is interface predicted distance error. ipSAE is a separately
calculated PAE-and-structure score. Treating those three values as synonyms would
make a convenient but scientifically false interface.

## What was done

- Added `RunResultsLoader`, which reads the durable formats already produced by:
  - Predict's `predictions.csv` and per-engine output directories;
  - iterative campaigns' `comparison_scores_long.csv`, falling back to
    `summary_all_runs.csv`;
  - RFdiffusion3's ranked `analysis/top100_manifest.json`.
- Added an RFC 4180 CSV reader because RFdiffusion3 can place JSON maps containing
  commas inside quoted CSV cells. It also normalises CRLF before parsing; Swift
  treats CRLF as one grapheme and an initial line parser silently returned no rows.
- Match every job in a directory-capable prediction batch to its own job-named
  structure. If several jobs share a directory and no safe match exists, omit the
  row instead of showing another job's model.
- Added one results browser with a selectable result list, the existing fully
  offline 3D viewer, engine/stage identity, metric cards, expandable/copyable
  sequence, and direct access to original structure and confidence files.
- Wired it into finished Predict runs, the completed iterative dashboard,
  RFdiffusion3's completion card, and every completed run in Activity/history.
- Added pLDDT beside iPTM in the older per-design structure inspector.
- Recognise engine-emitted pLDDT, pTM, iPTM, minimum interface PAE,
  `ipSAE(min)`, Boltz interface PDE, RFdiffusion3 minimum/mean iPTM, binding
  probability and ranking score. Missing values stay missing.

## Results

No performance measurements — implementation and correctness testing only.

The loader acceptance executable passed against one real IntelliFold JAX/MPS
prediction and two real iterative result structures in
`~/.iproteinstudio/projects/untitled_design`. Synthetic fixtures additionally
covered two jobs sharing one prediction output directory and an RFdiffusion3
ranked result with per-engine iPTM, minimum/mean iPTM, minimum interface PAE and
`ipSAE(min)`.

The real prediction was resolved to its normalised `model_0.cif` and displayed
the values actually on disk: pLDDT 51.6, pTM 0.280 and ranking score 0.360.
These are output values, not new benchmark measurements.

Both `swift build` and the release app bundle build passed under `caffeinate`.
The rebuilt Activity panel was visually inspected and showed an in-app results
action on completed prediction and iterative rows. The results sheet itself was
compiled and its data/view contracts were exercised, but a final screenshot of
the sheet was not captured because automated Space switching could not safely
take focus while the Mac was in active use.

## Decision and rationale

**Use one read-only browser over existing output contracts.** Rewriting or moving
outputs into a second library would create another source of truth and make
reproduction harder. The browser always exposes the original files.

**Show only metrics that an engine emitted.** Minimum interface PAE is labelled
as such, and Boltz `complex_ipde` remains interface PDE. `ipSAE(min)` appears when
an upstream scorer writes it, but Studio does not infer it from a different
number or claim to have calculated it.

**Do not vendor a new ipSAE computation in this UI pass.** The validated Dunbrack
implementation consumes both PAE and coordinates and is a scientific pipeline
stage, not a display transform. Adding it belongs at the prediction-output
boundary with provenance, checkpointing and tests across AF3/Boltz formats.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swift-cache \
caffeinate -dimsu swift build

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-release-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-release-swift-cache \
caffeinate -dimsu ./build_app.sh release

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-loader-clang-cache \
swiftc Sources/iProteinStudio/Models/RunResult.swift /private/tmp/main.swift \
  -o /private/tmp/iproteinstudio-results-loader-test
caffeinate -dimsu /private/tmp/iproteinstudio-results-loader-test
```

## Limits and what was not tested

- No predictor or design engine was rerun; this change reads existing completed
  outputs and does not alter a scientific launch path.
- `ipSAE(min)` recognition was tested with a fixture. None of the completed runs
  available in `~/.iproteinstudio` had emitted ipSAE.
- RFdiffusion3 ranked protein results were fixture-tested because no completed
  ranked campaign was present in the current Studio project directories.
- The browser shows ranked RFdiffusion3 structures. A dedicated paired apo/holo
  comparison with RMSD is still future work.
- No complete VoiceOver, keyboard-only, large-text or contrast pass was done.

## Next

Add the validated ipSAE scorer as an optional, checkpointed post-prediction stage
for protein complexes, then expose paired RFdiffusion3 apo/holo structures and
preorganisation RMSD in the same browser.
