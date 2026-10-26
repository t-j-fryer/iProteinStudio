---
entry: 0574
title: Sequence targets, base setup and intention-specific capabilities
date: 2026-10-26
author: Codex
type: implementation
status: implemented-with-qualification-limits
machine: Apple M4 Max, 64 GB unified memory
tags: [ui, install, rfd4, rfd3, predictors]
---

## Context

Follow-up to 0572. Recommended workflows need sequence input and colon-separated target assemblies. Base setup should contain RFD4, ESMFold2 Full, Boltz plus affinity, SolubleMPNN, AbMPNN and LASErMPNN. Custom workflows hid valid methods and exposed redundant or overly broad choices.

## What was done

Recommended forms now accept PDB/CIF or colon-separated complete target sequences. They use existing managed Full target preparation, shared Boltz per-sequence MSA resolution and explicit B/C/... target identities. Prediction must succeed before design starts. Hotspot syntax, chain ambiguity, sequence bounds and duplicates are checked before preparation. The scrollable form retains its action buttons. Closing the app during preparation leaves the managed target job in Jobs; automatic continuation is only attached to the open form.

RFD4 authoring, generation, MPNN and refolding now retain every selected target chain, including identical homomer chains. Protein and nanobody inputs preserve the target assembly coordinate group and explicit residue/hotspot mapping. Frozen sequence and alignment receipts are verified before reuse. Protein PDB input is converted by the native parser/writer. Native contig insertion left stale molecule instance IDs for multiple retained chains; the adapter reapplies AtomWorks' own ID/entity and instance annotations before strict validation, without changing bonds or coordinates.

Custom monomers now expose RFD4, native unconditional RFD3 plus refinement, and compatible X-token hallucination. Monomers omit target inputs and interface threshold controls. The custom Protein Hunter label is X-token Hallucination; the original named shortcut remains available. Redundant single-choice controls are hidden. Optimize restricts RFD4 to partial diffusion and inverse folding. Motif workflows include sequence-motif hallucination and a direct entry to the existing atomic-motif beta. General predictor-guided coordinate-motif hallucination is not represented as implemented.

Base setup selects RFD4, ESMFold2 Full, Boltz with affinity, SolubleMPNN, AbMPNN and LASErMPNN. Existing dependency expansion supplies the shared ESMFold2 runtime/ESMC encoder, control Python, chemical data and engine environments. The source CLI adds `--base`; setup copy distinguishes portable packages from source-build compiler prerequisites. Unsupported OS selections fail explicitly rather than being silently removed. New custom workflows use installed-base-compatible Full checking rather than implicitly requiring IntelliFold. Existing saved requests retain their settings.

The existing broker, immutable plans/code/runtime snapshots, shared execution lease and checkpoints remain in force. No weights are included or redistributed. Local app bundle built and opened; no public release or commit.

## Results

Technical acceptance passed on Apple M4 Max / 64 GiB; these are not performance or binding-efficacy measurements:

- `Tests/test_rfd4.py` (7), `Tests/test_design_workflows.py` (4), `Tests/test_rfd4_multichain.py` (3), `Tests/test_mcp_bridge.py` (24), all Swift contract harnesses, `swift build` and signed debug app build passed.
- `Tests/test_rfd4_multichain_inputs.py` passed real native CPU authoring/feature checks for protein and 7XL0 nanobody inputs with two target chains. Initial failures for PDB loading and stale molecule IDs are preserved with the passing rerun.
- One Full target prediction retained the two 96-residue SUMO chains B/C using auto MSAs.
- One native unconditioned RFD3 48-residue start and one Boltz X-token start each completed one SolubleMPNN/Boltz refinement cycle. Each has one optimized output and one separately counted cycle-00 start.
- One RFD4 48-residue binder against that exact Full-predicted two-chain input completed one SolubleMPNN beam proposal and Full refold. All three chains and both frozen target sequences survived unchanged; the shared alignment hashes matched target preparation.
- `output-audit.json` verifies exact cardinality, finite coordinates, confidence artifacts, immutable plan identities and RFD4/MSA receipts for all four managed jobs. Model/runtime fingerprints remain in plans and receipts.
- Native UI checks confirmed colon splitting, invalid-hotspot rejection, valid-input enabling, monomer method choices, the motif capability explanation, and the two RFD4 optimization choices. No scientific job was submitted through the UI.

The original enforced-memory Full attempt was blocked before inference (estimated 38.9 GiB versus the then-live 20.3 GiB budget). Following explicit user approval, bounded tests used recorded `memory_policy=override`; persistent app memory preferences were not changed. RFD4 memory estimates remain unqualified. CPU fallbacks were not enabled; upstream ESMC optional CUDA-fusion warnings and explicit empty-MSA warning for designed chain A remain in raw logs. Target chains used their requested alignments.

## Decision and rationale

Use existing target_prepare jobs and shared per-chain MSA cache/server resolution. Preserve each physical chain instead of joining sequences or discarding subunits. Keep the existing conservative minimum directional ipSAE across all protein chain pairs; do not invent a different multimer selection metric. ESMFold2 whole-chain X-token generation remains unsupported. Coordinate-constrained motif hallucination is distinct from existing sequence-motif preservation and is not implied by target-template support.

## Reproduce

Manifest and executable helpers: `Validation/experiments/studio_sequence_workflows_v1/`.
Evidence: `Validation/output/studio_sequence_workflows_v1/`.
Read bridge `results_overview` was saved before artifact auditing. Run `python3 -B Validation/experiments/studio_sequence_workflows_v1/audit.py` against those retained outputs.

Native CPU check: `NANOHUNTER_ROOT="$HOME/.iproteinstudio" "$HOME/.iproteinstudio/venvs/NanoHunter_rfd4/bin/python" -B Tests/test_rfd4_multichain_inputs.py`.
Swift checks: `python3 -B Tests/run_swift_contracts.py`; app: `bash build_app.sh debug`.
Managed test submission uses `managed_test.py start NAME` with a previously reviewed `NAME-plan.json`; it never launches an engine directly.

Before staging/testing, the queued and active production jobs were paused through the broker. Final adapters were staged under the exclusive lease with backups. Restore records preserve their original plan hashes and order in `active-resumed.json`, `queued-resumed.json` and `queue-restored.json`.

## Limits and what was not tested

No binding efficacy claims, speed comparisons, fresh-machine installation, full seven-cycle campaign or memory/long-campaign soak. The native nanobody multichain check was CPU authoring/featurization, not a new GPU nanobody campaign. The RFD3 monomer runtime smoke used Boltz refinement; the UI's Full refinement route was covered by request contracts and the separate multichain Full job, not an additional RFD3→Full runtime run. App interruption/automatic continuation after target preparation was not runtime-tested.

Whole-chain ESMFold2 X-token generation, fixed-framework RFD3 nanobody generation and general coordinate-template X-token scaffolding remain unsupported. Atomic-motif Protenix/IntelliFold template features have prior CPU checks only; inference/cycling are not qualified. Public RFD4 runtime distribution and clean-machine base installation remain pending. No scientific model defaults or performance claims were promoted.
