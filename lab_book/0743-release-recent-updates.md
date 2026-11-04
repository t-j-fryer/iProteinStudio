---
entry: 0743
title: Qualify and publish the accumulated Studio update
date: 2026-11-04
author: Codex
type: implementation
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

## Context
Explicit authorization to pause NESSO, complete GPU acceptance and publish the
recent app, MCP, CLI and release changes. The old0.2.32 draft/build78 remains held;
new build81/MCP53 replaces it only after the current source passes acceptance.

## Fix and validation
RFD4 ESM ligand scoring incorrectly resolved Boltz-standardized atom identity in
an ESM-only environment. Use the existing ESMFold2 native atom-map helper, preserve
input chemistry, and coordinate ligand export/audits in the pinned RFD4 runtime
(which has Gemmi). The resident model still executes in its pinned ESM runtime.
No environment or weights are modified. NISE keeps its existing supplied manifest.
Native chemistry identity/export/routing tests passed3 cases. Direct ESM-only export
testing exposed the missing Gemmi dependency and motivated explicit controller
routing rather than changing the installed environment.

## Release plan
Validation0360, experiment studio_release_032_v2: six shared workflow routes plus
paired T4 optimized/standard generation and T4 prediction with/without templates.
Use existing Studio preparation, immutable plan/start, GPU lease, caffeinate,
runtime snapshots and accounting. Inspect complete public diff before publication.
Old failed outputs remain immutable. NESSO paused through supported job control;
resume the original job after release checks and shared-asset installation.

## Limits
Technical software acceptance, not biological efficacy or new speed measurements.
GPU outcomes, package hashes and delivery results pending.
