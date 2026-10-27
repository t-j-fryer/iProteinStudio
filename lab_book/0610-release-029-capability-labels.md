---
entry: 0610
title: Release corrected 600M descriptions and acknowledgements
date: 2026-10-27
author: Codex
type: implementation
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [release, esmfold2, documentation]
---

## Context

Following [[0608-correct-600m-labels-and-credits]], the user requested delivery
of all corrections through the installed app, GitHub and release downloads.

## What was done

Prepare version 0.2.29, build 75 and staged MCP bridge 49 from the clean
correction worktree. The package contains the corrected 600M descriptions,
capability metadata, CLI/MCP/skill guidance and updated third-party notices.
README acknowledgements are already published on main. Preserve the existing
trusted-beta distribution channel and Sparkle signing key.

## Results

No performance measurements — release packaging only. Source qualification in
0608 passed Swift build, all 13 existing 600M regression tests and skill validation.
Release build, package checks and public-download verification are recorded below
when completed.

## Decision and rationale

Publish new immutable artifacts and a new update-feed entry rather than replace
0.2.28 downloads. Advance MCP_VERSION so the corrected bundled guidance is staged.
Keep scientific settings, weights and existing immutable job snapshots unchanged.

## Reproduce

```bash
swift build
bash release/release_app.sh --publish-unsigned-beta
```

Public asset verification uses the existing
`Validation/experiments/studio_release_027_v1/verify_distribution.py` with
`--version 0.2.29 --build 75` and a new output directory.

## Limits and what was not tested

No new inference, biological validation or hardware benchmarks are required for
these wording/metadata changes. No second-Mac or physical 16 GB test. The trusted
beta is ad-hoc signed with Sparkle-signed update archives, not Apple notarized.

## Next

Verify public downloads, install the verified bundle and record deployed versions.
