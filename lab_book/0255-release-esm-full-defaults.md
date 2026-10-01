---
entry: 0255
title: Publish ESMFold2 Full 3/50 defaults
date: 2026-10-01
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [esmfold2, defaults, release, mcp, cli]
---

## Context

User requests confirmation and synchronized app, MCP, CLI, GitHub and release.
Source already contains the explicitly requested Full 3/50 promotion, but the
installed build65 and installed shared scripts still resolve Full20/100.
The earlier local build64 promotion was superseded by build65, which intentionally
excluded the concurrent uncommitted defaults. This release combines both changes.

## What was done

Promote the shared Full profile to MSA128, three loops and 50 requested steps,
alongside direct adapter metadata, UI and schema descriptions. Correct the stale
Fast speed blurb: the historical4–13× comparison used Full20/100, whereas both
current default budgets are3/50. Preserve explicit overrides and frozen jobs.
Prepare0.2.20/build66/MCP38 from a clean checkout, excluding unrelated manuscript
and validation changes. Existing installed model weights require no changes.

## Evidence and decision

No new performance measurements. Promotion follows the user's explicit choice
and four-target, five-seed results in [0251](0251-queue-esmfold2-full-3-50.md).
All20 outputs passed the recorded geometry audit; MBP domain placement varied.
The final dimer timing has recorded concurrent-compilation confounding. This
is a user-selected throughput budget, not a universal accuracy-equivalence claim.
Prior adapter resume/ligand and Hunter stage acceptance remain applicable;
existing raw benchmark outputs are immutable and are not rerun for packaging.

## Reproduce and verification

Passed17 Python profile/adapter tests (including MCP normalization and frozen
20/100 overrides), all nine Swift executable contract harnesses, and swift build.
No running/queued jobs were reported before deployment. Publication and installed
checks follow below; evidence is under artifacts/0255-esm-release.

## Limits and what was not tested

No new GPU benchmark, full-campaign memory soak, fresh Mac install or independent
accuracy study in this release. Preserve manually paused jobs; do not resume them.

## Publication and pending staging

Published v0.2.20-beta from651516a; update-feed commit6d997a3. All four GitHub
asset sizes and SHA256 digests match local artifacts. The live feed identifies
build66/version0.2.20, and Sparkle verifies its archive signature. Local app66
is installed and open; app65 retained in build/app-backups.

A separate timing-repeat job85bc069eaa56 appeared after the initial idle check.
It is using immutable benchmark inputs. Do not interrupt it; shared pipeline
staging correctly waits for its execution lease. Production compilation and
packaging overlapped the beginning of this separately owned repeat; its own
quiet-host wait and host telemetry must be used when interpreting those timings.
This release makes no new performance claim from the repeat. Shared scripts
remain37/Full20-100 until the lease is released and the app stages the update.

## Final deployment verification

At21:20UTC the timing job released its lease and the app automatically staged
the update. Read-only verification passed: app0.2.20/build66; installed MCP38;
CLI and MCP normalize Full to MSA128/three loops/50 requested steps; an explicit
20/100 profile remains intact. All eight changed pipeline resource hashes match
the published app and source. See artifacts/0255-esm-release/installed-verified.json
and the repeatable verify_install.py. No weights were downloaded or copied.
The separately owned benchmark produced its final UNIT_DONE and then ended;
its broker status/error is preserved in benchmark-final.json for its owner.
No scientific jobs were stopped, resumed or modified by this release task.

The repeat's terminal failure was its explicit quiet-host audit:
`Host contention detected: retain outputs, do not promote these timing results`.
Both blocks logged five completed seeds/exit0 before the audit. Release compilation
is a possible contributor, not a proven sole cause. User informed; no timings
from this repeat promoted and no benchmark rerun started. Original0251 evidence,
with its previously documented caveat, remains the basis for the chosen default.
