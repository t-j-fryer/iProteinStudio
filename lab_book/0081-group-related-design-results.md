---
entry: 0081
title: Group related design results and restore saved hits
date: 2026-09-03
author: gpt-5.6
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, results, iterative, rfd3, validation]
---

## Context

An iterative campaign produced on an M1 Mac reported one design passing every
post-prediction filter, but its live Hits tab was empty. Browse Results displayed
the generated/design structure, complex reprediction and binder-alone prediction
as independent entries, while the live Structures and Hits tabs used a different,
less detailed data model. This follows the result provenance work in
`[[0074-make-rfd3-results-complete-and-movable]]`.

The supplied campaign was `untitled_prediction_2`: 12 runs, cycle 00 plus five
optimized cycles, Protenix Mini design and Boltz complex/binder-alone checks.

## What was done

- Replaced the live watcher's positional parsing of post-check CSVs with the
  shared RFC 4180, header-aware parser. The old parser expected the historical
  seven-column schema and attempted to parse the current `predictor` value
  (`boltz`) as iPTM, silently dropping every check.
- Preserved `is_hit` and `failed_filters` in live validation points. Independent
  checks now use the saved multi-metric verdict; design-stage points retain the
  user's interactive iPTM threshold.
- Added explicit scientific artifact roles and stable group identities to the
  durable result model. Iterative results group by run+cycle. RFdiffusion3
  results group by source backbone design.
- Added binder-alone structures to iterative durable results; these were written
  by the pipeline but omitted from the browser model.
- Added deterministic relocation of recorded absolute artifact paths when a
  complete campaign directory is moved or shared. Original CSV provenance is
  not rewritten.
- Added one shared grouped browser to the live Structures tab, live Hits tab and
  detached Browse Results window. Each design now presents generated/design,
  complex reprediction and binder-alone structures side by side with the scores
  and score engine belonging to each artifact.
- Changed score distributions and hit counts to count one value/verdict per
  design group rather than duplicating values for related structure files.

## Results

No performance measurements — implementation and result-integrity testing only.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Supplied M1 iterative campaign, reopened from a different path | 72 design groups | durable artifacts recovered | 192 |
| Supplied M1 iterative campaign | 60 optimized run/cycle groups | complete design + complex + binder-alone comparisons | 60 |
| Supplied M1 iterative campaign | 72 design groups | saved all-filter hits | 1 (`run_012`, `cycle_05`) |
| Existing RFdiffusion3 campaign | 8 source backbones | complete backbone + complex + binder-alone groups | 8 |
| Existing RFdiffusion3 campaign | 40 artifacts | backbone / complex / binder-alone | 8 / 16 / 16 |
| Build 15 trial package | 1 app + DMG + ZIP | package/resource/signature/launch/checksum contracts | pass |

The saved M1 hit has Boltz iPTM 0.911, ipSAE(min) 0.739, binder pLDDT
0.942, target-aligned binder-pose RMSD 1.80 Å and binder-alone RMSD 1.46 Å.
These are values read from that campaign's saved CSV, not a new inference run.

## Decision and rationale

The unit shown in the sidebar and counted as a hit is now a **design**, not a
structure file. Structure files remain individually inspectable inside the
design because each answers a different question. A group passes if at least one
recorded independent-check verdict is true; the presentation layer never
reconstructs a multi-metric verdict from whichever scores happen to be visible.

We retained cycle-00 groups and design-stage scores for diagnosis, but only saved
independent multi-filter verdicts populate the all-filter Hits surface. This
keeps the separate “design-stage iPTM hit” concept from being confused with a
verified hit.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

bash Tests/test_iterative_results_ui_contract.sh
bash Tests/test_rfd3_results_ui_contract.sh

CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-swift-cache \
SWIFT_MODULECACHE_PATH=/tmp/iproteinstudio-swift-cache \
swiftc Tests/PredictionResultsContractHarness.swift \
  Sources/iProteinStudio/Models/RunResult.swift \
  -o /tmp/iproteinstudio-results-contract
/tmp/iproteinstudio-results-contract
/tmp/iproteinstudio-results-contract iterative \
  '/Users/thomasfryer/Downloads/untitled_prediction_2'
/tmp/iproteinstudio-results-contract \
  '/Users/thomasfryer/.iproteinstudio/projects/untitled_design/rfd3_runs/rfd3-20260902-220705'

CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-swift-cache \
SWIFT_MODULECACHE_PATH=/tmp/iproteinstudio-swift-cache \
swiftc -parse-as-library \
  Sources/iProteinStudio/Models/ProteinSequenceInput.swift \
  Sources/iProteinStudio/Models/Predictor.swift \
  Sources/iProteinStudio/Models/RFD3Request.swift \
  Sources/iProteinStudio/Models/DesignRequest.swift \
  Sources/iProteinStudio/Models/DesignPoint.swift \
  Sources/iProteinStudio/Models/RunResult.swift \
  Sources/iProteinStudio/Core/ResumeContract.swift \
  Sources/iProteinStudio/Core/TemplateWriter.swift \
  Sources/iProteinStudio/Core/CommandBuilder.swift \
  Sources/iProteinStudio/Core/MetricsWatcher.swift \
  Tests/IterativeCommandContractHarness.swift \
  -o /tmp/iproteinstudio-iterative-results-contract
/tmp/iproteinstudio-iterative-results-contract

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
CLANG_MODULE_CACHE_PATH=/tmp/iproteinstudio-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iproteinstudio-swiftpm-cache \
swift build --triple arm64-apple-macosx15.0 \
  --scratch-path /tmp/iproteinstudio-results-build

release/release_app.sh --unsigned-beta --allow-dirty
hdiutil verify \
  build/unsigned-beta-0.2.0-15/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg
bash Tests/test_clean_machine_app_launch.sh build/iProteinStudio.app
(cd build/unsigned-beta-0.2.0-15 && shasum -a 256 -c SHA256SUMS.txt)
```

## Limits and what was not tested

No new protein inference was run because this change does not alter predictors or
scientific pipelines. The exact M1 campaign and an existing RFdiffusion3 campaign
were parsed end to end, and the native app compiled, but this pass did not perform
a manual results-window click-through on the M1 machine or test VoiceOver. The
packaged app was launch-tested away from the source checkout, but this does not
exercise every result-view interaction. RFdiffusion3 groups
with multiple MPNN sequences intentionally remain one source-backbone group;
future feedback may justify a nested backbone → sequence hierarchy.

## Next

Exercise the grouped comparison at the minimum supported window size on both M1
and M4 hardware, then consider synchronized camera orientation across its
side-by-side structure viewers.
