---
entry: 0279
title: Simplify NISE and expose native region design controls
date: 2026-10-02
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [ui, nise, rfd3, protein-hunter]
---

## Context
The user requested simpler NISE setup, standard selective affinity/residency, deeper
RFD3 Advanced controls and native Protein Hunter region modes. Clarification explicitly
selected existing Protein Hunter sequence modes, not RFD3 cycle-00 region modes.

## Implementation
NISE's first section contains ligand and generation setup, with cohort import in a
disclosure. New requests use Boltz scoring, screens off, selective affinity on and one
resident Boltz worker. Two workers remain opt-in. Adaptive proposals remain off and
explained in Advanced. Ligand-local X controls are removed from the app; legacy backend
fields and saved-run policies remain for resume. New UI drafts enforce the current policy.

Native partial redesign preserves outside-region sequence and restricts MPNN redesign;
sequence motifs preserve motif identities, without fixed coordinates. Motif mode requires
Boltz and a supported MPNN designer. Both retain the existing per-trajectory scheduler;
separate generators are blocked. CLI motif generation now forwards the recorded seed.
MCP plans expose and validate the same mode arguments. No new science algorithm.

RFD3 Advanced exposes existing steps, recycles, queues, batching, precision, seeds,
exact lengths, motif presets and partial structured preference. Quick defaults unchanged.

## Evidence
Swift build, 14 Swift unit tests, the CLI contract and all request/command harnesses passed. 66 NISE tests passed with installed
Boltz Python and NANOHUNTER_ROOT pointing to its chemical dictionary. 24 MCP tests passed.
Real partial/motif seed helpers passed: unchanged outside-region identities, motif identities
and same-seed replay. Bundled RFD3 partial/motif examples passed real Foundry preflight.
Initial broad NISE invocation used the wrong environment/missing chemical dictionary;
rerun with installed Boltz dependencies passed. No new throughput numbers were measured.

## Reproduce
Run Tests/run_swift_contracts.py, Tests/test_native_hunter_regions.py,
Tests/test_rfd3_worked_examples.py, test_mcp_bridge.py, and unittest discovery for
`test_nise*.py` with the installed Boltz Python and runtime root. Build with swift build.

## Limits
No fresh full neural Protein Hunter region campaign, biological validation, performance
comparison, fresh-Mac installation, or prolonged memory soak in this UI release. The
native upstream science/scheduler remains unchanged except deterministic motif seeding.
Figure3 job-465040f858d2 was broker-paused and protected by queue HOLD during compiler
and packaging work, and must resume using its frozen settings after deployment.

## Delivery
Version 0.2.22 / build 68 / MCP 40. Clean release packaging excludes unrelated prototype,
new artwork and manuscript work in the shared checkout.

Published v0.2.22-beta from source 1c912ca, update feed 4ec18d7. Installed the exact
release bundle in /Applications; previous build retained in build/. MCP doctor reports
bridge 40 / ok; installed detection reuses existing weights and environments. Native app
inspection confirmed both Protein Hunter menu options. The computer-use service then
lost its native pipe, preventing further NISE/RFD3 visual inspection; Studio stayed alive.
This is an explicit visual-QA limitation, not a passed visual check.

Resumed Figure3 job-465040f858d2 through the broker with its original immutable digest,
removed only this maintenance HOLD and restored the ordered watcher. No new scientific
settings, outputs or calibration conclusions were added by this release.
