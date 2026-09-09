---
entry: 0019
title: Restart helix-strength benchmark with geometry recorded only
date: 2026-09-06
author: Codex
type: benchmark
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [predictors, geometry, monomer, benchmark, mcp]
---

## Context

Following 0101, the user explicitly requested removal of the peptide geometry filter while retaining violations, authorizing a benchmark restart. A Boltz baseline cycle00 had C–N=2.28 Å against the diagnostic 2.2 Å threshold; the old policy rejected it before MPNN could act. This decision concerns generic target-free monomers. No inference that later prediction necessarily repairs the defect is made.

## What was done

`validate_prediction_geometry.py` now separates advisory distance violations from unreadable/non-finite/empty coordinate errors. Its default CLI records atomic geometry_report.json (relative structure path, SHA256, residues, atom pair, distance, thresholds); distance violations return success. Boltz/IntelliFold/resident wrappers retain unusable-input failures. All iterative engines and cycle-wave outputs receive a normalized pred_min report through the frozen pipeline script. MCP cycle overviews expose report path/counts without changing hit verdicts. MCP11 / bridge1.5.1; app build22 planned.

Preserved concurrent NISE and other app changes. Cancelled the superseded v2 job through Studio and stopped only its campaign controller. Fresh v3 declares all 210 trajectories / 1,050 optimization cycles at the same seeds, strengths and native engine settings, with record-only geometry for all initial/intermediate/final structures. Old outputs are retained separately, never pooled or overwritten.

## Results

Six executable geometry tests and four existing predictor tests passed. They exercise peptide violation success, immutable coordinates/checksum, valid zero record, unusable-input failure, normalized symlink output and actual Boltz wrapper. MCP full suite initially had one sandbox socket-bind error; elevated rerun pending. Full benchmark and package checks pending. No performance measurements claimed.

## Decision and rationale

Distance thresholds are diagnostic, not eligibility rules. Continue usable intermediate predictions; report final defects alongside confidence and secondary structure. Restart rather than pool trajectories selected by the previous geometry gate. Preserve exact seed pairing, all failures, model inventories, bridge plans, shared GPU lock, and empty MSA. This is a requested workflow policy change, not a scientifically demonstrated quality improvement.

## Reproduce

Working commit: `37cc95497283025191e7d2067cb35d1af9168d72` plus recorded working-tree modifications.

- `python3 -m unittest discover -s Tests -p test_geometry_reporting.py -v`
- `python3 -m unittest discover -s Tests -p test_prediction_engine_safety.py -v`
- `python3 -m unittest discover -s Tests -p test_mcp_bridge.py -v`
- `Validation/experiments/helix_strength_all_engines_v3/campaign.py`: stage, prepare, run with managed Protenix Python.

See Validation entry0019 and v3 manifest/stage receipt for exact settings, code/checkpoint hashes, hardware, MSA policy and commands.

## Limits and what was not tested

No experimental folding claims. Recovery of the actual rejected trajectory is not yet measured. Full seven-engine run, graphical app interactions and final release checks pending. Historic geometry.validate API remains diagnostic for old audit scripts; those frozen campaigns retain their original rejection criteria.

## Next

Complete v3, inspect geometry persistence through cycle05, and compare secondary structure across strengths within each engine.

## Declared analysis

P-SEA from coordinates; primary endpoint trajectory mean across cycles01–05, equal weight per trajectory; cycle00 explicitly excluded. Three paired contrasts per engine with 10,000 bootstrap draws, seed906026, no multiplicity adjustment. All geometry violations remain in endpoints. Report per-cycle violations and whether initial violations are absent at cycle05; no automatic claim that MPNN repaired a specific bond. Native engine settings / OpenFold X substitution limit cross-engine comparisons. Same 90-aa, 50% mask, SolubleMPNN, initialization-only strengths0/.5/1, binder seed906000 + global index, MPNN1906000 +1000*global index +cycle, prediction seed42, one sample, empty MSA, scheduler run/maxparallel1. No weights copied into the repository or distribution.

## Execution update, 2026-09-06 21:40 UTC

Seven geometry execution tests, four predictor wrapper tests, all17 MCP tests (including elevated loopback test), four monomer scheduler/coordinate tests, two campaign matrix contracts and the iterative CLI contract passed. The exact previously rejected mmCIF was rechecked into a separate v3 preflight report: one C–N violation, no coordinate errors, exit0, original bytes unchanged.

V3 manifest SHA256 `aba3a91b42ec6d48231c9e68c92e20e8288bf7058659b7c299d2d0d4dffc3057`; controller PID2102. First baseline pilot job `job-f0eab240b8f4` completed five cycles and passed the independent sequence/cardinality/confidence/MPS/geometry-report audit (six structures including cycle00). Controller progressed to the remaining nine baseline trajectories through a new immutable plan. Raw outputs and all six per-cycle geometry reports preserved.

Runtime snapshot is MCP11/bridge1.5.1. Concurrent source development advanced to MCP12/bridge1.6.0 and app build23 (NISE backbone selection); these changes are preserved. Packaging initially caught a stale hard-coded resource version assertion; the current combined app is being packaged against the updated MCP12 assertion. Benchmark source bytes remain separately frozen.

## Package verification and handoff

The combined current app **0.2.0 build23 / MCP12** passed the release Swift build, bundle resource contract and code-signature checks. The local DMG passed hdiutil verification; read-only mount verification confirmed exact equality of the runner, geometry reporter and all three affected predictor wrappers to the v3 scientific snapshot. ZIP and DMG SHA256 values are recorded in `Validation/output/helix_strength_all_engines_v3/package_verification.json`. App: `build/iProteinStudio.app`; DMG: `build/unsigned-beta-0.2.0-23/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`. Ad-hoc local beta only; no publishing, model-weight redistribution, Applications installation or graphical interaction testing.

Fresh managed MCP code successfully returned geometry diagnostics on all six real pilot cycles. The already-connected read MCP server has cached the old Python module and requires reconnection to show the new optional fields; its connection was left intact. New processes and the app package include the updated catalog.

Implementation, focused tests and package verification are complete. The full v3 benchmark continues under PID2102 with per-cohort audited checkpoints and automatic final report/figures. Recovery of the previously rejected global trajectory8 remains to be measured; the reporting-only recheck above did not execute MPNN or prove recovery.

## Progress and NISE deployment recovery

Both Boltz baseline jobs completed: 10/10 trajectories, 50 optimization cycles, 60 structures including initialization. All outputs now pass the independent sequence/cardinality/confidence/MPS/report audit. Global trajectory8 has one C–N violation at cycle00 and zero flagged geometry violations at cycles01–05; it completed successfully. This is one observed recovery, not a general guarantee about geometry repair.

The controller halted at 2026-09-06T21:56:47Z because concurrent deployment changed MCP11 to12. Reviewed diffs are confined to four MCP help/version files and five NISE-only scripts; no monomer runtime, sampler, geometry thresholds, predictor code, checkpoint or seed change. Exact nine-file hashes and full diff are recorded in `deployment_recovery_v1/amendment.json` and `reviewed.diff`. Every other original engine/model fingerprint remains required, with full hash verification passed. Original manifest/audits/raw data remain immutable. Three recovery tests pass, including rejection of unreviewed scope and predictor-code drift. Recovery controller is `Validation/experiments/helix_strength_v3_deployment_recovery_v1/recover.py`; it audits completed jobs in place and continues untouched plans through Studio. No reruns/replacement seeds or app changes in this recovery.

## Completed, 2026-09-07

The fresh v3 campaign completed all210 trajectories/all1,050 optimization cycles with zero failures. Full raw-hash and coordinate replay passed. Final analysis and five figure sets: `Validation/output/helix_strength_all_engines_v3/analysis/full_analysis_v1/`. See project entry0104 / Validation entry0020.
