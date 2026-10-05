---
entry: 0297
title: Recheck RFD3 motif fix deployment
date: 2026-10-05
author: Codex
type: audit
status: complete
machine: Apple Silicon; CPU-only source and patch tests
tags: [rfd3, motif, coordinates, deployment]
---

## Context

The user asked to check Studio motif scaffolding against an external report of
placeholder-biased COM centring and supplied the earlier entry0293 findings.

## What was done

Re-read the earlier audit and current GUI/MCP motif origin handling. Compared
all eight available source/test/overlay hashes in0293 with their current files,
including the active managed Foundry package and the isolated corrected copy.
Applied the current correction in memory to the installed source and compared
its resulting hash with the previously exercised corrected package. Re-ran the
three patch migration/idempotence/selection-semantics tests; all passed.

## Results

All eight hashes are unchanged. Active Foundry input_parsing.py remains
79839c6d6e1f952df87db2c0b347e9805681b8028070db5e4ddac6ebf2b8f770,
with the old broad annotation-preservation patch. The corrected result remains
64f53c95c2591853b6e951d082f5e3143b86f809cc283c9c7f491d486ed40024.
The runtime selection fix has therefore not been deployed.

The previous coordinate-preprocessing findings remain applicable: normal motif
mode omits COM overrides; default centring uses fixed target plus motif atoms,
excluding generated placeholders. Explicit all-atom COM was shown unsafe in
the earlier audit. Its nine-requested/33-fixed atom example concerns the separate
selection bug. Partial diffusion was validated separately in0293.

## Decision and rationale

No need to repeat identical preprocessing experiments for this deployment
status check. Keep the scientific distinction clear: Studio's normal motif
origin policy avoids the external failure mechanism, but atom-specific motif
conditioning still needs the corrected managed runtime. Do not describe an
unreleased source fix as fixed in the installed app.

## Reproduce

Evidence: artifacts/0297-rfd3-deployment-recheck/audit.json and patch-tests.log.
Tests: managed RFD3 Python, `-m unittest discover -s Tests -p test_rfd3_rasa_patch.py`.
Earlier complete preprocessing reproduction and measurements are in0293.

## Limits and what was not tested

No new coordinate-preprocessing matrix, model execution, clash-rate tests,
benchmark, runtime modification, deployment, build or release this turn. The
external report's quality figures are not measurements from this Mac.

## Next

Package the corrected selection patch into a new managed runtime, perform small
motif and partial-diffusion end-to-end checks through the job manager, then
promote that runtime. Motif-only origin remains a separate optional workflow
change requiring deliberate qualification.
