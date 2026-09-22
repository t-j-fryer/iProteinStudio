---
entry: 0178
title: Diagnose and repair MPSGraph scratch filesystem stalls
date: 2026-09-22
author: GPT-6
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [mps, reliability, runtime]
---

## Context

Follow-up to0177. Earlier Boltz/PSICHIC tests passed, but final checks stalled in MPSGraph's shared temporary directory. User now authorizes a reversible repair and requests stable behavior for other users. Do not assume directory state is the cause until paired testing.

## Plan and limits

Manifest/code: `Validation/experiments/mps_scratch_recovery_v1`. Compare retained previous and published Boltz runtimes with identical frozen settings under the managed broker. Preserve all existing scratch contents if replacement is needed. Repeat actual inference and PSICHIC reference scoring after repair. Record recurrence and output fidelity. Fresh Mac, other chips and multi-day stability remain untested. No scientific defaults will change.

## Initial evidence

Job `job-190a46a4a4be` reproduced the MPSGraph `mkdirat` stall in the previously qualified Boltz torch2.14 environment. The120-second limit fired; termination also waited on the kernel call, so the coordinator exited before the published arm. The original failed attempt is retained and is not a completed paired comparison. Process inspection subsequently confirmed that worker exited. The new bounded filesystem probe independently detected the shared-folder stall in5.58seconds; its child exited. Published-runtime stalls were already sampled in0177.

The one-time contents-preserving folder repair was authorized by the user and submitted only after no active managed jobs or inference workers remained. Its receipt is saved under `Validation/output/mps_scratch_recovery_v1`.

## Repair and repeated inference

The original directory (inode61771182,177,435,904bytes of directory metadata) was renamed intact to `com.apple.MetalPerformanceShadersGraph.studio-backup-20260922T185332Z`; a same-permission empty replacement was created. No contents were deleted. The bounded probe then passed in0.025seconds. The small count observed in the replacement during inference remained responsive; the old directory's metadata size alone does not establish its file count or why it became pathological.

Job `job-f07d9889f284` completed12 full-setting Boltz predictions: two fresh processes per runtime, three resident requests per process, with both the retained previous and published torch2.14 runtimes. All12 CIFs are byte-identical to the earlier qualified baseline; PAE/PDE matrices and scalar confidence scores match exactly. No new geometry errors or breaks. Saved elapsed times are diagnostic only because other testing/indexing occurred concurrently.

PSICHIC job `job-2283a3ddedec` passed64 CPU-reference cases using GPU ESM batches8 and CPU graph scoring, with maximum absolute scalar difference0.000396938 (gate0.001); completed resume loaded no model and shortlist plumbing passed. The second installed-patch64-case run (`job-6483113da27a`) passed the same gates and resume check. The installed public Boltz prediction (`job-cc3c4f3ce390`) completed1/1 folds with0 failures. Both MCP23 jobs recorded successful GPU-storage probes (0.026 and0.034seconds respectively).

## Product behavior

MCP23 adds a bounded subprocess check before managed GPU jobs dispatch. It tests only creation/removal of its own uniquely named empty folder, with no enumeration, cache deletion or automatic shared-folder replacement. A failure is recorded in `gpu_storage.json`; the job reports a clear restart/resume instruction before models launch. Seven tests cover real child timeout, preserving unrelated contents, absent-directory behavior, symlink rejection, child failure and broker failure/retry dispatch. All18 MCP regression tests and2 snapshot tests passed; Swift builds in both checkouts.

## Remaining limits

This demonstrates recovery after replacing the affected directory, not the origin of its condition or universal immunity to GPU hangs. No fresh-Mac/other-chip/multi-day soak was performed. The health check specifically catches this filesystem failure before inference; it is not a blanket GPU watchdog. The published runtime packages and all scientific defaults remain unchanged.

## Distribution

Patch release0.2.2 build45/MCP23 carries the startup guard and support guidance. Scientific runtime archives are unchanged. Publication receipt will be recorded after the app bundle, GitHub asset digests and Sparkle feed are verified.

Publication verified: [0.2.2 build45](https://github.com/t-j-fryer/iProteinStudio/releases/tag/v0.2.2-beta), source `0d9404c`, update feed `0cb2c36`. All4 GitHub asset SHA-256 digests/sizes match the local build; live appcast and EdDSA signature verify. The exact app is installed in `build/iProteinStudio.app`, build44 retained under `build/previous-apps`. Managed MCP23 and bundled pipeline source match in324 resource comparisons. Relaunch loads the new app. Receipt: `Validation/output/mps_scratch_recovery_v1/RELEASE_VERIFICATION.json`. Final storage probe passed in0.025seconds, with238 observed entries, backup inode preserved and no active jobs. No repeat stall occurred in this bounded qualification.

Automatic approval initially rejected the combined publication command over default-branch/scope concerns. Read-only verification established that main was unprotected and unchanged at the commit parent; the exact scoped commit and ordinary non-force fast-forward were then approved. No branch protections were bypassed.
