---
entry: 0105
title: Add a target-agnostic binding helix-strength benchmark
date: 2026-09-07
author: Codex
type: implementation
status: complete; aCbx v7 benchmark and audit complete
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1
tags: [secondary-structure, protein-binding, predictors, validation, mcp]
---

## Context

Following the complete target-free comparison in entries 0101 and 0104, the
user requested the same control during protein-binder design, restricted to
helix-kill strengths 0 and 1. The initially identified bundled target was
alpha-cobratoxin, but the user then requested a reusable script so a non-toxin
sequence and MSA could be supplied instead.

The hypothesis for the scientific campaign is that strength 1 reduces
binder-chain helicity relative to paired strength 0 while retaining useful
predicted interface scores. This implementation does not test that hypothesis.

## What was done

Added `Validation/experiments/binder_helix_strength_all_engines_v1/` with a
target-agnostic campaign controller, output auditor, fixed declaration and
usage guide. The design contains seven installed predictor variants, strengths
0 and 1, ten paired 90-aa trajectories per arm and five optimization cycles.
SolubleMPNN, one predictor sample, exact paired initialization/MPNN seeds and
the Studio-selected measured scheduler are fixed within each engine.

The first prepare requires a target slug, one canonical-protein FASTA and an
A3M or Stockholm MSA. It rejects multiple FASTA records, noncanonical target
residues, fewer than two aligned sequences, and a query that does not exactly
match the target after standard gap/A3M-insertion removal. Exact input bytes and
checksums are frozen in ignored output; subsequent calls fail on drift. The
script assumes no target structure and no epitope.

Every one-trajectory arm pilot is planned, run and independently audited before
any remaining nine-trajectory cohort can start. Plans use the public immutable
MCP plan/start path, required target-MSA policy and shared GPU lock. Audits replay
initialization and seeds; check native/normalized cardinality, binder chain A,
fixed target chain B, confidence, Apple-GPU evidence and record-only geometry;
and report trajectory-level P-SEA, iPTM, optional ipSAE(min), confidence and
paired bootstrap contrasts. Cycle 00 is excluded from scientific endpoints.

The supplied target was subsequently the bundled aCbx example. The v1 broker
correctly rejected its first plan because the generated template was outside
the managed runtime/import roots; this happened before inference and no plan
was persisted. Rather than widen filesystem policy, v2 froze a managed-runtime
copy of the alignment and generated the broker template beside it. Its first
Boltz pilot completed, but the independent audit incorrectly searched the
per-run directory for native resident output. V3 followed the normalized
structure symlink to its native prediction leaf, then exposed a second audit
assumption: resident/cycle-wave jobs emit per-batch rather than per-run exit
receipts. V4 accepts either layout only after checking zero exit codes for every
cycle, complete cardinality and a completed broker state. Earlier output is
retained as provenance and is not reused.

## Results

Seven target/matrix unit tests passed. All 28 pilot/remaining argument vectors
passed the production MCP normalizer. The supplied aCbx FASTA contains one
71-aa canonical sequence; the query-matched A3M contains 1,148 records and has
SHA-256 `377a3af41f6816683c9b06241fafd2e0c2bc6b0129c2f4a78387ad36f75f34cf`.
The new structure reader also parsed one preserved
historical two-chain Boltz output, verifying exact binder/target chain identities,
P-SEA, confidence, iPTM and ipSAE(min) extraction without new inference.
`stage-preview` confirmed that all 14 staged
pipeline files currently match the managed runtime byte-for-byte.

V4 was staged and prepared with manifest SHA-256
`06c249a12d9c86336456fb9e197097bc860a9636603de6f784cd6b7348f349e0` and
stage-receipt SHA-256
`983671d67bda3ba5b6e30e66fce0056723746462eaec3e229da2edfba58e75ce`.
Nine tests pass, including resident native-link and scheduler exit-receipt
regressions. The complete v4 audit was replayed with writes disabled against
the preserved v3 Boltz output and passed before v4 was prepared. All 14 v4
one-trajectory plans were reviewed. The fresh v4 `boltz_h0` pilot then completed
and passed its independent audit (receipt SHA-256
`f95d8af921e4da5ad5dd96178360ce1744191e31902d89c6fc474119b787a6f6`);
the remaining pilot matrix began. It stopped safely after the first IntelliFold
pilot because that engine does not emit Boltz's `complex_plddt` key.

At the user's direction, v5 declares `complex_plddt` and ipSAE(min) optional and
engine-conditional while retaining iPTM as required. Eleven tests pass, including
missing-optional-metric and resident-MPS-evidence regressions. A complete v5
audit replay against the preserved IntelliFold pilot passed before preparation:
six structures, all completion and chain checks passed, six null
`complex_plddt` values, ipSAE present, and final iPTM 0.507. V5 was staged with
receipt SHA-256
`3dc25ec4752d73b42e78d9cbfbf348d8efc53c7fb9edb51b7d15f62ba9ad0850`
and prepared with manifest SHA-256
`afee13c04e66af09045d35eb9ac54822b21642e130b3ca51841d4ccf8ac57208`.
All 14 pilot plans were reviewed, and the full gated controller started at
2026-09-07T20:09:27Z. It runs all pilots before creating the 126 remaining
trajectories. No paired scientific contrast is reported while incomplete.

### Completion update (v5-v7)

V5 completed 12 of 14 pilots, then the managed planner correctly refused to
launch OpenFold with an unsupported resident scheduler. The planner now fixes
OpenFold to the established per-run scheduler, with an MCP regression test.
V6 proved that scheduler correction but exposed two further fail-closed issues:
OpenFold's upstream raw-MSA reader silently ignored the valid target alignment
because its basename was not a recognized database stem, and the controller's
cohort gate operated per arm instead of across the full pilot matrix. No v6
expanded cohort was allowed to continue.

V7 losslessly copies each explicit A3M/Stockholm alignment into a private
per-chain `colabfold_main` slot before constructing the OpenFold query, and
requires all 14 pilot audit files to pass before the first remaining arm can
start. The OpenFold strengths 0 and 1 pilots were run first and both passed.
All 14 v7 pilots then passed before the global gate opened.

The full v7 campaign completed at 2026-09-08T11:05:45Z. All 140 declared
trajectories completed: 14 arms x 10 trajectories, with five optimized cycles
and one cycle-00 structure each (700 optimized and 140 initialization
structures). All 28 pilot/remaining audits passed and froze 23,449 raw-file
hashes. There were 57 cycle-05 iPTM hits at the declared 0.7 threshold. Geometry
warnings were retained under the declared record-only policy: 13 trajectories
had at least one warning across their six structures, while one trajectory had
two warnings at cycle 05; no coordinate set was unusable.

Strength 1 reduced mean optimized binder helicity in all seven predictor
variants. The paired 10,000-resample 95% bootstrap interval excluded zero for
Boltz (-21.8 percentage points), IntelliFold Flash (-32.6), OpenFold3 (-17.1),
Protenix Constraint (-29.0), and Protenix Mini (-41.4); it crossed zero for
IntelliFold Full (-14.4) and Protenix v2 (-1.8). Every paired mean-iPTM interval
crossed zero, so this n=10 computational benchmark does not resolve an iPTM
effect of the initialization strength. Intervals are unadjusted for
multiplicity, and predictor scores are not experimental binding evidence.

## Decision and rationale

Keep target choice outside versioned configuration but freeze it at first
prepare. This permits a non-toxin target without weakening reproducibility or
silently reusing a mismatched MSA. Use only strengths 0 and 1, as requested, and
retain the seven-variant matrix so the result is directly comparable in scope
to the completed monomer benchmark. Interface scores remain computational
screening signals, not experimental binding evidence.

## Reproduce

Base commit: `37cc95497283025191e7d2067cb35d1af9168d72`, with the repository's
existing dirty working state. The target, alignment, staged runtime and
engine/checkpoint inventory are frozen in the v7 manifest. Its SHA-256 is
`4ba8855fed8f38afe46fb73387b9e9fc73d6a716f814b4d6d21fa4d59e87c391`;
the staged-runtime receipt SHA-256 is
`8853fa01eca498828b1514fff476f9ef0b93d163ac07bd58b225c37e864c2088`.

```bash
python3 -m unittest discover -s Validation/experiments/binder_helix_strength_all_engines_v7 -p 'test_*.py' -v
PYTHONPATH=Sources/iProteinStudio/Resources/pipeline/mcp python3 -c 'from iprotein_mcp.plans import _normalize_iterative_arguments'
python3 Validation/experiments/binder_helix_strength_all_engines_v7/campaign.py status
```

The target-specific commands are documented in the experiment README.

## Limits and what was not tested

The supplied example is a toxin, despite the earlier request for a reusable
non-toxin-capable script; the controller itself remains target-agnostic. No
experimental binding, efficacy, safety, cross-engine score-calibration, or
cross-engine speed conclusion is made. No multiplicity correction, target
structure, epitope, orthogonal post-predictor, or wet-lab validation is
included. The managed results catalog does not index these external Validation
output roots, so the required `results_overview` attempt failed closed and the
immutable campaign audit/report was reviewed directly.

Final verification passed: 13 v7 campaign tests, 17 MCP bridge tests, the full
workflow-pipeline contract test, and `swift build`.

## Next

Use a new immutable campaign version and its own frozen FASTA/MSA for a future
non-toxin target. Treat the observed helix effect as a target-specific
computational result until it is repeated on that target and validated
experimentally.
