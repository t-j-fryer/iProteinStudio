---
entry: 0038
title: Unify multichain input and backend routing
date: 2026-08-25
author: codex-gpt-5.6
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [multimer, ui, msa, iterative-design, rfd3, predict]
---

## Context

Protein inputs were superficially single-chain. A colon typed into several UI
fields was silently removed by a generic sequence cleaner, concatenating two
subunits into one sequence. Plain prediction had a multi-chain backend but no
consistent compact input, iterative design reused one target MSA on every
non-binder protein, and RFdiffusion3 represented only one target chain. Residue
selection also stored bare numbers, so residue 25 was ambiguous in a multimer.

The intended scientist-facing contract is one compact syntax everywhere while
each backend receives its own exact native representation.

## What was done

- Added `ProteinSequenceInput`, the shared strict parser for colon-separated
  protein subunits, and a reusable UI that immediately reports the count,
  assigned IDs, full sequences and lengths.
- Plain Predict expands one colon-separated fold to protein chains A/B/C and
  appends shared or row-specific protein partners after those chains.
- Iterative and RFdiffusion3 design reserve chain A for the generated binder;
  fixed target subunits are B/C/D. Iterative templates now emit one protein
  entry per target and accept chain-qualified hotspots on every emitted target.
- Changed structure selection from bare residue numbers to values such as B34
  and C34 in both py2Dmol and the legacy 3Dmol surface layer.
- Made target preparation predict a real multimer with one auto/cached MSA
  policy per chain instead of concatenating sequences.
- Reworked iterative target-MSA handling to create a chain-to-MSA manifest.
  Every target MSA is independently query-validated. A single
  `--target-msa-path` override is rejected for a multimer because its ownership
  is ambiguous; explicit per-chain YAML paths remain supported.
- Reworked the RFdiffusion3 protein campaign to generate, checkpoint and pass a
  distinct exact MSA for each fixed target subunit.
- Added dependency-free PDB/mmCIF protein reading. External RFdiffusion3 target
  chains retain their user-facing identities during inspection, then are copied
  to a campaign-local PDB and atomically remapped B/C/D at the backend boundary.
  The contig and chain-qualified hotspots are remapped with the coordinates, so
  an ordinary A/B target cannot collide with binder chain A.
- Versioned target-prediction cache keys around the new chain-preserving input.

## Results

No performance measurements — implementation and routing validation only.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Swift iterative command contract | 1 suite | result | pass |
| Swift workflow request contract | 1 suite | result | pass |
| Python workflow pipeline contract | 1 suite | result | pass |
| Iterative CLI contract | 1 suite | result | pass |
| Swift package build | 1 build | result | pass |
| Release application bundle | 1 build | result | pass |
| Synthetic plain-predict complex | 3 chains | assigned IDs | A/B/C |
| Synthetic RFdiffusion3 target | 2 chains | distinct MSA paths retained | 2/2 |
| Synthetic external A/B target | 2 chains | normalized target IDs | B/C |
| Synthetic mmCIF target | 2 chains | parsed and materialized to PDB | 2/2 |

## Decision and rationale

The colon is the only compact multimer separator in sequence fields. It is
visually obvious, easy to paste, and already familiar from protein-folding
interfaces. FASTA records and lines continue to mean separate prediction jobs;
a colon within one record means subunits of that one fold.

Chain names are assigned centrally, not independently by predictor adapters.
Predict has no privileged chain and starts at A. Both design workflows reserve A
for the molecule being designed, so targets begin at B. RFdiffusion3 external
structure names are not forced on the user: the campaign stores both the source
mapping and a normalized target artifact for exact reproduction.

One MSA may never be silently copied across unrelated target sequences. Separate
query validation and a persistent manifest cost a little orchestration but
prevent a backend from accepting scientifically invalid alignments without an
obvious runtime error.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

bash -n Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh

caffeinate -dimsu env PYTHONPYCACHEPREFIX=/private/tmp/iproteinstudio-multichain-pyc \
  /Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  Tests/test_workflow_pipelines.py

caffeinate -dimsu bash Tests/test_iterative_cli_contract.sh

# The two Swift contract binaries were compiled with ProteinSequenceInput.swift
# plus their production request/writer sources, then run under caffeinate.
caffeinate -dimsu /private/tmp/iproteinstudio-iterative-contract
caffeinate -dimsu /private/tmp/iproteinstudio-workflow-contract

caffeinate -dimsu swift build
caffeinate -dimsu bash build_app.sh
```

## Limits and what was not tested

- No new GPU inference or long design campaign was launched. The change was
  tested at the exact request, YAML, chain, MSA and structure-handoff boundaries.
- Synthetic PDB and mmCIF fixtures covered two target subunits. Larger chain
  counts use the same mapping but were not passed through RFdiffusion3 itself.
- The dependency-free mmCIF reader covers the standard `_atom_site` loop emitted
  by the installed predictors. Exotic multiline atom-site values and non-letter
  RFdiffusion3 chain IDs remain deliberately unsupported.
- Paired MSAs/cross-chain co-evolution are not constructed. Each target subunit
  receives its own unpaired query-matched alignment, matching the current
  predictor adapters' validated behavior.

## Next

Run one small two-subunit target through each installed prediction engine and a
minimal RFdiffusion3 protein campaign when GPU acceptance time is next allocated.
Retain the resulting campaign manifest as an anonymized end-to-end multimer
fixture if redistribution permits.
