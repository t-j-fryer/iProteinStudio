---
entry: 0489
title: Implement atomic motif beta workbench
date: 2026-10-21
author: Codex
type: implementation
status: in-progress
machine: Local Apple Silicon Mac; no inference performance measured
tags: [rfd3, motifs, templates, ligands, mpnn, beta]
---

## Context

Following [[0487-review-artios-enzyme-benchmarks]] and
[[0488-plan-transferable-atomic-motifs]], the user requested implementation as
a beta testing mode, including the appropriate motif template for folding.
The working checkout already contained substantial unrelated changes, including
a new memory-admission policy that blocks unqualified RFD3/ligand inference.
Those changes were preserved.

## What was done

- Added the native RFdiffusion3 **Atomic motif beta** workbench, exact source
  atom display, bounded pilots and paired comparison settings.
- Vendored original AME-41 fixtures/specs and BSD licence with the audited
  inventory. Prepared all 41 portable-on-recreation, checksummed case bundles.
- Added strict managed desktop plans and the private runner, retaining shared
  code/runtime snapshots, execution ownership and memory protection.
- Fixed RFD3 export to retain per-atom ligand chain/residue/component identity;
  duplicate atom names across different molecules are now distinct. Legacy
  single-ligand fixtures remain readable; old multi-ligand fixtures are rejected.
- Added frozen root maps, source/full motif RMSD, pocket-aligned per-ligand
  centroid and pose RMSDs, strict fold/identity gates, greedy/beam selection,
  equal-budget allocation, sequence deduplication and operation receipts.
- Added LigandMPNN fixed-side-chain inputs and LASErMPNN B-factor locks plus
  CCD-based per-component protonation without changing heavy coordinates.
- Implemented the eight-arm Boltz cycling runner around the existing resident
  predictor. Guided proposals and untemplated ranking checks remain separate.
- Added positional motif template exporters for Boltz, Protenix v2 and
  IntelliFold; only Boltz is wired into automatic beta cycles.

## Results

No inference performance measurements — implementation and CPU input tests only.
The chemistry audit found 38/41 cases with matching CCD heavy-atom sets. BCA in
M0024, DHS in M0054 and MAY in M0731 need explicit variants. This is **not proof
of Artios' excluded-case identities**. Exact hashes/chemistry are retained in
`artifacts/0489-motif-beta/chemistry.json`.

Executed tests/build results and logs are retained in the same artifact folder.
Synthetic orchestration outputs test software behavior, not scientific success.
Swift build and local ad-hoc-signed app assembly passed; the packaged app contains
all 41 cases. Selected CPU suites passed (motif contracts, native inputs, managed
plan/provenance, RFD3 export, memory policy and five existing template adapter
tests); the existing motif scoring regression also passed. The full existing
template suite has one driver-entrypoint failure because the newly present memory
gate stops that test before its fake predictor. It was recorded rather than
disabling the guard. See `verification.json` for exact test counts and log hashes.

## Decision and rationale

Use mapped residues from the generated RFD3 scaffold for template features,
with absent coordinates elsewhere. Boltz's native parser preserves the exact
intended query positions. Original catalytic atom geometry remains immutable
and is scored separately. Tip-only coordinates cannot supply general backbone
template features, and a full scaffold template would be a different intervention.

The current checkout's memory gate blocks RFD3, ligand and guided inference.
The new workflow deliberately obeys the same gate; file preparation is allowed.
No guard was disabled and no model job was launched to bypass it. Inference
readiness is therefore unfinished, which is why this entry remains in progress.

## Reproduce

See [beta guide](../docs/MOTIF_BETA.md) for the UI and CPU workbench commands.
Tests: `Tests/test_motif_beta.py` (Protenix Python for Biotite),
`Tests/test_motif_beta_native.py` (Boltz Python),
`Tests/test_motif_beta_bridge.py`, `Tests/test_rfd3_target_export.py`,
`Tests/test_memory_admission.py`, and existing template/motif-score regressions.
Build: `swift build`; local app assembly: `bash build_app.sh debug`.

## Limits and what was not tested

No real RFD3 generation, MPNN sampling, prediction, different-family final check,
lab experiment or scientific yield/throughput benchmark. Protenix/IntelliFold
native features and inference remain unqualified. No arbitrary custom motif
import UI, partial ligand chemistry, symmetry-aware atom matching, clash gate,
or automatic final assessor. Interrupted directory predictions can be rerun;
the beta's complete-operation resume is less granular than production campaigns.
No installed runtime, current GUI session, active campaign or model weights were
modified. The development app contains this checkout's pre-existing edits too.

## Next

**Follow-up correction:** entry [[0490-support-original-motif-residue-templates]]
found that the small native parser test here did not cover repeated query
residues. Unmodified Boltz can realign sparse coordinates incorrectly. The new
marked-file positional adapter and all-41 audit supersede this entry's broader
mapping assumption; original/native residue templates are now supported too.

Qualify memory profiles through Validation; then execute a 1-root end-to-end
pilot with both real designers and inspect their masks/output identities. Test
native features for each additional templated predictor before automatic cycles.
