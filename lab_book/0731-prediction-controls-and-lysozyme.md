---
entry: 0731
title: Simplify prediction controls and replace the protein example
date: 2026-11-04
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [ui, prediction, examples, rfd4, public-candidate]
---

## Context

The user requested typed RFD4 family budgets, useful Metal speed/accuracy help,
one Prediction setup form and an explicit template switch. They then replaced
the earlier cobra-toxin default request with T4 lysozyme and experimental PDB/CIF.
The 4TW1 file was an existing imported Bgx workspace template, not a built-in
example; the old example button incorrectly retained a previous template.

## What was done

Families now uses the existing validated numeric editor without arrows. Invalid
text blocks Start; valid text updates the saved budget immediately. Prediction
has one form with alignments, sampling, throughput and engine controls. Guidance
is explicitly enabled/disabled, retains file choices while off, and omits the
template from actual run configuration while disabled. Existing saved guided
requests migrate to enabled. Selecting the new example clears stale template
choices, offers its bundled matching structure, and starts with guidance off.

T4 lysozyme (RCSB 2LZM) replaces the shipped cobra-toxin example and default
protein CLI YAML. Original PDB/CIF downloads are retained unchanged with hashes.
The derived target keeps all 1,309 protein atoms/164 residues and identical
coordinates, remapping chain A to B. FASTA agrees with observed residues and
SEQRES; CIF atom identity/coordinates agree with PDB. No MSA is bundled or
silently substituted. App, CLI and MCP guidance describe this. Examples resolve
from the current app bundle so beta does not need to stage shared runtime files.
No existing saved targets, settings, alignments or completed runs were rewritten.

Metal help cites existing measurements, not new benchmarks: Labs 0502/0506 show
5.48–12.93% and a separate additional 8.17–12.21% reduction, respectively, for
warmed unconditional 64/128-residue generation on M4 Max (40 GPU cores, 64 GB).
Those are distinct baselines, not an asserted combined speedup. Lab 0514's
216-token target-conditioned first-call check was 41.498279/41.673889 seconds
standard/optimized, n=1 each, with exact outputs and no speed gain. Exact tested
output agreement does not establish general biological accuracy or binding yield.

## Results and reproduction

No new scientific speed or accuracy measurements. Run:

- `python3 Tests/test_lysozyme_example_integrity.py` (three file-integrity tests).
- `STUDIO_SWIFT_CASES=prediction_templates,engine_batch_controller,rfd4_configuration,workflow_requests python3 Tests/run_swift_contracts.py`.
- `bash Tests/test_iterative_cli_contract.sh`.
- `swift build` and `bash release/build_local_beta.sh`.

Contracts cover on/off execution payloads, persistence, old-request migration,
missing-file/engine restrictions and replacing a stale example template. Beta
is 0.2.32-dev/build79; public source has matching build79 changes. UI inspection
used a separate app identity and isolated synthetic workspaces with inert runtime
markers. It verified T4 example wording, a single Prediction form, template
fields appearing/disappearing, typed family count27, rejection of0, recovery to27,
and expanded Metal evidence. No jobs were launched from the preview. The initial
preview lacked runtime markers and complete fixture fields; these fixture-only
problems were corrected. The first inspection call was unusually slow.

Logs/evidence are retained under `lab_book/artifacts/0731-prediction-controls/`.

## Limits and release state

No new prediction/design campaign, binding validation, performance benchmark,
MSA generation or engine installation. Independent GPU qualification for the
previous 0.2.32 features stopped at the missing Boltz import in an ESM ligand
route (Lab0727). This UI/example change does not resolve that failure. The old
build78 draft remains unpublished; its automatic gate is stopped. Build79 must
be packaged and qualified before public binary delivery. Installed stable app,
public main/appcast and existing jobs remain unchanged.

Sources: https://www.rcsb.org/structure/2LZM and the original downloads recorded
in the bundled provenance.json. 4TW1 identity: https://www.rcsb.org/structure/4TW1.
