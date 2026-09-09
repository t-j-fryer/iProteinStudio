---
entry: 0101
title: Simplify helix control and benchmark installed predictors
date: 2026-09-06
author: gpt-6
type: implementation
status: complete
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1
tags: [secondary-structure, monomer, predictors]
---

## Context
User requests a single initialization-only helix-kill strength, updated app/DMG/MCP, and strengths 0, 0.5, 1 for all installed predictors: 90 residues, ten trajectories, five optimization cycles. Previous complete campaign: project 0100 / Validation 0017.

## What was done
Implementation and validation in progress. Preserve historical outputs and unrelated source changes. Retire other public controls; retain legacy fields to detect incompatible saved requests.

## Methods
Paired initialization/MPNN seeds across strengths and engines. Seven installed predictor variants, 21 arms, 210 declared trajectories, 1050 optimization outputs; cycle00 excluded. One trajectory per arm is an end-to-end smoke included in ten. Remaining nine require audit. Empty MSA, SolubleMPNN, normal MPNN after initialization. Record engine-specific input handling (OpenFold substitutes supported spike residues for X), native model defaults, fingerprints and failures. No replacement seeds. P-SEA on predicted coordinates; trajectory is statistical unit.

## Results
Implementation validation: Swift debug/production builds passed; Swift request/migration contracts passed; 17 MCP contracts, 18 initialization/journal/coordinate contracts, 7 sampler compatibility tests, 2 campaign declaration contracts, CLI and release/update contracts passed. Historical journal library tests remain; the public mutation/refinement interface is retired.

App 0.2.0 build19, MCP10/bridge1.5.0 packaged with the existing unsigned-beta process. DMG integrity, mounted app resource/signature checks, binary/resource equality and archive checksums passed. Local artifact only; no publishing or installation into Applications.

DMG SHA256: `4e9fde3c75efffe909e69a11a33991227e828a5a66d18854d63b03582551ef84`.
ZIP SHA256: `2c07c299cb490326a6cba706dc74824924712809bac72255e0afa80c31cb3811`.

Scientific benchmark started 2026-09-06T18:06:50Z, controller PID15883. Current outcome pending; no efficacy conclusion yet. 21 pilot plans are recorded. First Boltz2 trajectory is running through the public MCP broker.

## Reproduce
Declared manifest: `Validation/output/helix_strength_all_engines_v1/manifest.json`, SHA256 `0ae592a0cf2b7b269abac253a2b402f16cf8dfef3406bfa422bf5340ea10e42d`.
Stage receipt SHA256: `327fd513e07ba502f6d3f925d612de054a80625d43c7d0194eb893a8b84f48dd`; records hardware, detected engines, model/checkpoint hashes, source/installed engine code, lock files and MPS availability. Empty MSA means no cached-MSA checksum. Base commit `37cc95497283025191e7d2067cb35d1af9168d72`; dirty source hashes recorded.

```bash
python3 Validation/experiments/helix_strength_all_engines_v1/campaign.py stage
python3 Validation/experiments/helix_strength_all_engines_v1/campaign.py prepare
python3 Validation/experiments/helix_strength_all_engines_v1/campaign.py run
release/release_app.sh --unsigned-beta --allow-dirty
```

The first unused preflight was archived under `helix_strength_all_engines_v1_unused_preflight` before any job start. Source whitespace cleanup required a fresh staging receipt. Packaging initially failed its old MCP9 resource assertion; updated to10 and repackaged. Sandbox Swift build failed to access compiler caches; the normal approved build passed. Synthetic integration fixtures were updated for retired inspection; all18 passed after removing their expectation of a live refinement journal. No scientific retry or replacement occurred.

## Limits and what was not tested
The new scientific campaign is pending completion. GUI interaction, cross-Mac installation and notarization were not tested. No cross-engine efficacy or performance conclusion yet.

## Next
Monitor/audit all pilot and remaining trajectories. Complete paired within-engine structural analysis and report failures without replacing seeds.

## Corrected continuation and final package

All three Boltz2 pilot trajectories completed and passed full raw-output audits. IntelliFold Flash failed in calibration before inference: Bash3 raised `template_environment[@]: unbound variable`. Corrected empty template-array expansion in monitored, ordinary and cycle-wave launch paths, preserving populated arguments. The new contract executes the shipped launch lines with empty/populated arrays and paths containing spaces; it passed, as did the CLI contract. No model or scientific setting changed.

Continuation uses `Validation/experiments/helix_strength_all_engines_v2`. Its manifest pins the three original pilot audit checksums and reuses those trajectories in n=10; their raw files remain in v1. The failed IntelliFold job `job-3bb3bff84004` remains recorded. No scientific seed was replaced, and the failed launch produced no predictions. Controller23244 started the remaining207 unique trajectories through the same public bridge.

Latest app/DMG: 0.2.0 build20, MCP10. Production build, resource/signature checks, DMG integrity, mounted contents/permissions/symlink equivalence and archive checksums passed. DMG SHA256 `c9493687a34b2fba819033afc404cd2e410eee08ff47975c88a93f3e759af57b`; ZIP SHA256 `3e3b9ee443468b39bc5e177a10b8fea2b6b049c8c34d4b3a8fb575884558b2d7`. Build logs are preserved alongside artifacts. Older builds18/19 remain on disk.

Fresh MCP processes expose the v10 helix-only guide and reject retired flags. The already-open read connector caches older Python modules/help and requires reconnection to load the new interface; it is not evidence of the staged source behavior.

`Validation/experiments/helix_strength_analysis_v1/finish.py` adds all three paired strength contrasts per engine (including0.5vs1) and exportable SVG/PNG figures after the complete audited campaign. No current efficacy conclusion is drawn from the pilot n=1 per arm.

V2 manifest SHA256: `4118e575ec13b4ad109ea55d68c0d25ccedb7dfe572737e4e86948af1ebd5bb9`.

The v1/v2 engine-code and engine/checkpoint SHA256 inventories compare identically. Four pilots are now audited (all three Boltz strengths and IntelliFold Flash baseline). The complete-review script passed a 210-outcome synthetic matrix test, including the expected exact0.5-to1 paired difference and generated SVG/PNG/Markdown artifacts. Its background observer waits for the full audited report and records a blocked controller rather than labelling an incomplete campaign complete. Current pointer: `Validation/output/helix_strength_all_engines_current.json`.

## Source-reference recovery (2026-09-06, 19:45 UTC inspection)

The controller paused at19:41:11Z after OpenFold3 strength0.5 completed. Twenty trajectories had completed inference; nineteen had passed output audit. The sole mismatch was the working-tree `mcp/iprotein_mcp/catalog.py`: unrelated NISE display/help additions. The live runtime still matched every declared staged-file hash. No monomer runner, sampler, assessor, seed, model or setting changed.

`Validation/experiments/helix_strength_source_recovery_v1/recover.py` records the drift and creates an exact source-reference copy from runtime files verified against the original stage receipt. It retains the original manifest, immutable experiment-code checks, runtime hashes, engine/checkpoint checks, output audits and public MCP plan/start/lock paths. It does not overwrite the ongoing app edits or any completed scientific output. This resolves the mutable-working-tree dependency by using the original bytes, rather than relaxing a checksum.

The pending OpenFold3 output passed the unchanged structural audit:20 audited trajectories and100 optimized structures. No prediction was repeated. The continuation skips only completed, hash-reverified audit units and executes the existing remaining budget. It runs the full report/figure analysis in the same protected source context after completion.

Reproduce: `MPLCONFIGDIR=/private/tmp/helix-recovery-mpl ~/.iproteinstudio/venvs/NanoHunter_protenix/bin/python Validation/experiments/helix_strength_source_recovery_v1/recover.py audit-pending` then `recover.py run`. Recovery receipt: `Validation/output/helix_strength_all_engines_v2/recovery_source_v1/receipt.json`. Full campaign results remain pending; no strength ranking is established from n=1 pilots.

## Retained Boltz geometry rejection and independent-cohort continuation

Progress inspection at2026-09-06T21:10Z found that all21 pilots passed, then the first remaining cohort (`remaining__boltz_h0`, job `job-4b90914b956f`) completed8/9 and stopped the controller at20:11:47Z. Localrun007/globaltrajectory8 failed in cycle00: chainA residues13–14 had C–N=2.28Å above the original2.2Å gate. Total:29 completed/audited trajectories,145 optimized outputs,1 retained failure;180 trajectories remain unstarted.

The frozen geometry validator independently reproduces the same defect. Rejected input sequence/cardinality, finite90-residue CA confidence, native error attribution and raw checksums were also verified. `Validation/experiments/helix_strength_geometry_recovery_v1/continue_campaign.py` preserves `operational_passed=false`, the failed trajectory and its original audit. It records a separate failure-review receipt and permits other independent conditions to continue. It does not retry or replace seeds, alter inference parameters or weaken geometry validation. Failed pilots, unstarted units, unclassified failures, integrity drift and failures without matching geometry diagnostics still halt.

The controller retains the prior exact-source-reference, original immutable manifests/experiment hashes, engine/checkpoint checks, MCP plan/start and shared execution lock. All original21 pilot gates remain required before cohort expansion. Final means/paired intervals continue to exclude failed trajectories and explicitly report n.

Commands: managed Protenix Python `continue_campaign.py review`, `python -m unittest discover -s Validation/experiments/helix_strength_geometry_recovery_v1 -p test_continue.py`, then `continue_campaign.py run`. The controller gate suite was initially blocked before running by a concurrent runtime MCP README change; verification is pending. Receipt: `Validation/output/helix_strength_all_engines_v2/recovery_geometry_v1/reviews/remaining/boltz_h0.json`. No new model inference was performed for diagnosis. Full comparison remains pending.

A concurrent NISE-only runtime deployment then changed MCP README/catalog and four `scripts/nise/` files. The monomer runner, seed sampler, assessor, MCP plan builder/schema, all prediction engines and checkpoint metadata remained unchanged. The exact six deployed files were checked against the working tree, diffed against original snapshots, and recorded in `recovery_geometry_v2/non_monomer_deployment.json` with SHA256/size/mtime. Original manifests are unchanged. The explicit supplemental verifier checks those six reviewed hashes and every original monomer/engine/checkpoint hash; it does not accept future drift automatically or overwrite the NISE deployment. The monomer runner contains no `scripts/nise` invocation.

Final continuation code: `Validation/experiments/helix_strength_geometry_recovery_v2/continue_campaign.py`. Four retention/controller gate tests passed against the actual failed cohort and negative fixtures. The original failed audit stays false. The first v1 test attempt ran zero tests because deployment drift blocked setup; no success is attributed to it.

## Completed, 2026-09-07

The fresh v3 campaign completed all210 trajectories/all1,050 optimization cycles with zero failures. Full raw-hash and coordinate replay passed. Final analysis and five figure sets: `Validation/output/helix_strength_all_engines_v3/analysis/full_analysis_v1/`. See project entry0104 / Validation entry0020.
