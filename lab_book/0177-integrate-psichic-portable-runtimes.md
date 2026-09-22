---
entry: 0177
title: Integrate experimental PSICHIC and publish portable engine runtimes
date: 2026-09-22
author: GPT-6
type: implementation
status: qualified
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [psichic, install, runtime, recovery, ui, release]
---

## Request and scope

Integrate PSICHIC wherever NESSO can screen ligand candidates, explicitly label it experimental, and complete portable distribution, recovery/rollback, exact job preservation and shared engine adapters. The user explicitly authorized GitHub publication and accepted macOS26.0/26.2 **minimums**. Fresh-Mac acceptance testing is deferred. Canonical repository baseline: `72792adb6edf0df1a33ffecc60795cca963ef5c5`; release source is isolated in `.worktrees/portable-release`, preserving unrelated local figures/experiments and Lab Book edits.

## Implementation

- App, CLI and MCP offer experimental PSICHIC with MPS ESM batch8 and CPU graph batch16/four threads. Rank by `1 − predicted_nonbinder`; retain affinity and all class probabilities. No invented entropy/placement score. NESSO remains the saved-setting default; Boltz retains NISE structural verification and its final objective.
- Twelve optional standalone-CPython runtime archives, SHA-256 inventories, relocatable native libraries/console scripts, app-owned trusted catalog and separate verified upstream model downloads. General installation uses these profiles without Git, compiler or pip builds; source builds require explicit developer opt-in. Existing measured NESSO cache, Flash padding and Torch2.14 Boltz/IntelliFold profiles are preserved.
- Durable activation journals recover interrupted version/alias/receipt switches and retain previous installations. Preflight captures portable runtime identities, adapter/bridge code and independent model-data copies before jobs enter the queue. Derived configuration copies bind runtime paths without changing saved scientific requests. Workers reject altered inventories; aliases include every MPNN variant. Legacy installations must migrate before receiving this preservation guarantee.
- Shared registry/adapters own capabilities, mappings, scheduling and dispatch without replacing upstream scientific settings. UI and installer enforce native OS minimums. App requires14; Protenix v2/Mini profiles require26.0, OpenFold3/RFD3 profiles26.2. Host26.6.1 satisfies both.

## Qualification

Machine above only; no controlled throughput claim. Frozen requests use unchanged seeds, full diffusion/recycle settings and guidance. Prediction fixture: ubiquitin76, explicit empty MSA. RFD3: unconditional76 residues; CPU sequence tools use benign fixed backbones/fluorescein fixture. Raw outputs are immutable under `Validation/output/portable_runtimes_v1`.

**All 14 paired scientific checks passed**: Boltz2, IntelliFold Flash/full, Protenix v2/Constraint, OpenFold3, RFD3, AntiFold, NESSO, ProteinMPNN, SolubleMPNN, LigandMPNN, AbMPNN and LASErMPNN. Boltz/IntelliFold saved coordinates/confidences were identical; four MPNN modes and repaired LASErMPNN sampled sequences were identical. Other differences remained inside the declared audit gates. Exact per-engine metrics, archive hashes/OS minimums and source attempts are in [release_qualification.json](../Validation/experiments/portable_runtimes_v1/release_qualification.json).

PSICHIC production integration:64 CPU-reference cases, job `job-464a74702499`, output `psichic_smoke_20260920T152640Z`; maximum absolute differences: affinity0.000381455, antagonist0.000361204, nonbinder0.000396937, agonist0.000063375, all below0.001. Completed resume loaded no model; score/lineage-selection plumbing also passed. Final Python/Finder metadata cleanup does not change model/native computation.

Final package set: **2,938,147,290 compressed bytes**,12 archives; no learned model weights. Required LASErMPNN static chemical tables/dataset IDs are explicitly inventoried separately. Final archives passed relocation/import checks, including space/Unicode paths; GitHub's stored SHA-256 and sizes match all12. Current-Mac final migration job `job-c7c2fedd9eac` completed with `NHDONE|ok` for all requested components. Resource backups are retained under `~/.iproteinstudio/backups/studio-resources/0177-*`.

## Tests

Required `swift build` passed in canonical and isolated release checkouts. All eight native Swift contract harnesses passed. MCP bridge18 tests, including actual execution after live adapter/model changes; runtime suites10 tests, including six real hard-exit activation boundaries, rollback, tamper rejection, independent model copies and MPNN alias binding; code snapshot2; installer3; shared adapters1; prediction safety4; RFD3 scheduling3; ligand screening14; NESSO18; PSICHIC4; resident resume14 with1 optional skip; NISE geometry/ordering5. Empty-root detection/system-only PATH exercises the no-Apple-Python-shim path. These tests do not substitute for a fresh Mac.

## Failures retained and corrected

- Earlier package builds exposed absolute native dependencies/RPATHs and editable-source assumptions; assembler repairs internal links and rejects unresolved external dependencies. Python sysconfig/config scripts and package metadata now relocate; Finder metadata is excluded.
- First paired launcher resolved away virtualenv identity and enabled forbidden fallback; corrected before the paired qualification. A missing multiprocessing main guard caused OpenFold/NESSO test-worker re-entry; corrected reruns passed (`job-41ded8cf3be8`, `job-e2353a2cbe55`). Frozen raw failed outputs were retained.
- Initial final-audit import path was wrong, so an independent reader audited immutable outputs and read Boltz's separate PAE/PDE NPZ files. No failed run was relabeled successful.
- Blanket `.pt` exclusion removed LASErMPNN's static geometry tables. Restored only the eight required upstream non-weight data files from commit `5df210fced6764d83f01425d1fc4319a22b70c2a`; real CPU inference matched exactly (`job-f6756efa0510`). Learned checkpoint remains separate.
- Tests exposed stale source-string assertions after shared-adapter extraction and fixture assumptions about live installation paths; updated tests exercise the intended retained-runtime behavior. NISE test invocation initially lacked its required root environment; corrected invocation passed.

## Reproduction and publication

Scripts/manifest under `Validation/experiments/portable_runtimes_v1`; packaging tools under `tools/`; raw logs, immutable requests, package manifests and release checksum audits under `Validation/output/portable_runtimes_v1`. Scientific runs use the managed preflight/job broker and shared execution lease. App release target:0.2.1 build44, MCP22; immutable runtime tag:`runtimes-2026.09.20-1`. Publication completion and installed public-MCP smoke receipts will be appended after verification.

## Limits

No fresh-Mac installation, other Apple-chip qualification, Developer ID signing/notarization, new complete NISE optimisation campaign or biological binding experiment. This remains the existing ad-hoc-signed trusted-beta channel with Sparkle EdDSA-signed app updates. Current-Mac installation and paired relocation are not evidence that every supported Mac has been tested. No diffusion/recycle reductions or model-size changes were promoted by this work.
