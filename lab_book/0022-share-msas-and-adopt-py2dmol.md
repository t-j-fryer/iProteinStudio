---
entry: 0022
title: Share exact target MSAs and adopt py2Dmol everywhere
date: 2026-08-18
author: codex-gpt-5
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, predictors, msa, ui, viewer]
---

## Context

The RFdiffusion3 **Predict structure & pick hotspots** action produced a visibly poor
fold for the bundled 71-residue alpha-cobratoxin target, while the same sequence looked
correct in Predict. The two buttons did not in fact run the same scientific input:
`TargetPredictor` wrote `msa: empty`, whereas Predict indexed and reused exact-sequence
alignments. This violated the fail-loud and noob-proof requirements and followed the
workflow-contract audit in [[0020-audit-rfd3-predict-contracts]].

Structure display also used three separate 3Dmol WebKit wrappers for target picking,
result browsing, and thumbnails. The requested py2Dmol renderer was not present.

## What was done

`TargetPredictor` now creates a one-job `PredictionConfig` and launches the same
`predict_batch.py` entry point used by Predict under `caffeinate`. Protein chains request
`msa: auto`; the shared policy searches the managed MSA cache, examples, projects, and
prior prediction outputs by exact first-record sequence, requires at least two records,
and calls the alignment server only on a miss. A versioned result directory prevents an
older `msa: empty` target fold from being returned as if it met the new contract.

The shared `TargetPrepView` supplies both iterative design and RFdiffusion3. RFD3 now
also sets the adopted monomer chain to `A`, matching the generated structure rather than
retaining its historical `B` default.

The RFdiffusion3 protein campaign already had exact-sequence, depth-checked cache-first
MSA reuse. Iterative design has now been brought into the same policy: its runner searches
the managed target cache, examples, projects, and prior output before native generation,
validates the chosen MSA, and publishes newly generated A3Ms back to the shared cache.
Explicit `--target-msa-path` and a real template MSA continue to take precedence. A new
`scripts/find_target_msa.py` helper makes this behavior independently testable.

py2Dmol was vendored from upstream commit
`70e9b96b395d061a8b2aa9e83a10a568126eaed6`, with its license and provenance retained.
`Py2DmolViewer` is now the shared offline PDB/mmCIF viewer for target preparation,
completed-run browsing, dashboard tiles, and generated thumbnails. Its Style panel
exposes tube/cartoon rendering, presets, geometry, outlines, shading, orthographic
projection, color modes including pLDDT/chain/rainbow/secondary structure, colorblind
mode, rotation, and PNG save. Residue selection is bridged back to Swift for hotspot
picking. The prior 3Dmol target renderer remains only behind the explicit hydrophobic
surface toggle because py2Dmol does not calculate a solvent-accessible surface.

## Results

The real target-prep entry point was exercised with IntelliFold v2-flash and the bundled
71-aa alpha-cobratoxin sequence. It found the existing exact alignment instead of
contacting the server, folded successfully, and wrote an mmCIF that the new viewer read.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| exact cached target alignment | 1 | distinct sequences in A3M | 8,024 |
| IntelliFold v2-flash, 71-aa target | 1 | fold wall time reported by pipeline | 46.2 s |
| same fold | 1 | mean pLDDT | 89.8 / 100 |
| same fold | 1 | pTM | 0.7194 |
| real WKWebView, generated mmCIF | 1 | parsed positions | 71 |
| real WKWebView PNG snapshot | 1 | PNG bytes | 506,290 |

The real WebKit harness also passed PDB and mmCIF loading, residue selection round-trip,
Style-panel opening, switching to Cartoon, presence of pLDDT coloring, and PNG export.
The iterative CLI, RFD3/plain-prediction Python, and native request contract suites pass.

## Decision and rationale

An MSA is selected by content, never by filename or directory. Exact query equality plus
depth of at least two prevents the common but silent errors of attaching another target's
alignment or treating a query-only file as evidence. Network generation is a cache miss,
not a tab-specific default.

py2Dmol is the normal viewer because it provides a compact publication-style renderer
and user-facing style controls without a web service. Keeping 3Dmol as the explicit
surface mode is preferable to pretending py2Dmol supplies a calculation it does not.
RDKit remains the 2D ligand editor/picker; that is chemical editing, not protein
structure viewing.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh
caffeinate -dimsu /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  Tests/test_workflow_pipelines.py

CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
SWIFT_MODULECACHE_PATH=/private/tmp/iproteinstudio-swift-cache \
swiftc -parse-as-library \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/RFD3Request.swift \
  Sources/iProteinStudio/Models/PredictionRequest.swift \
  Tests/WorkflowRequestContractHarness.swift \
  -o /private/tmp/iproteinstudio-workflow-contract
caffeinate -dimsu /private/tmp/iproteinstudio-workflow-contract

env CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swift-cache \
  caffeinate -dimsu swift build
caffeinate -dimsu ./build_app.sh release
codesign --verify --deep --strict --verbose=2 build/iProteinStudio.app
```

## Limits and what was not tested

- The measured fold is one 71-aa monomer, one seed, IntelliFold v2-flash, and one M4 Max;
  it is acceptance evidence, not a model-quality benchmark.
- No new real Boltz, full IntelliFold v2, AlphaFold 3, or OpenFold-3 target-prep fold was
  launched. They receive the same generated YAML/MSA policy through the shared runner.
- Multi-chain, nucleic-acid, and arbitrary ligand rendering were not exercised in the
  WebKit harness. PDB and mmCIF protein parsing were.
- The py2Dmol PNG data path passed, but the macOS download/save dialog was not exercised.
- Hydrophobic surface mode intentionally remains 3Dmol and was not changed or retested.
- VoiceOver, keyboard-only control traversal, dark appearance, and minimum-size layouts
  have not had a complete accessibility pass.

## Next

Add an XCTest UI harness that opens a completed run, changes py2Dmol style and coloring,
then opens RFdiffusion3 target preparation and clicks a residue, so the full SwiftUI
presentation is covered in addition to the real WebKit bridge.
