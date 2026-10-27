---
entry: 0610
title: Release corrected 600M descriptions and acknowledgements
date: 2026-10-27
author: Codex
type: implementation
status: complete
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
Release Swift build and packaged-resource contract passed. All 13 existing 600M
regression tests passed again. Bundled `studioctl.py doctor` reports bridge 49
and the expected separate read/run/admin profiles.

Published [v0.2.29-beta](https://github.com/t-j-fryer/iProteinStudio/releases/tag/v0.2.29-beta).
Release source/tag: `a89b09bb31291c0f2b5b728ff58c0bad9872fff2`; initial feed commit:
`8981a8e`. Independent public downloads passed GitHub asset digests, SHA256SUMS,
Sparkle EdDSA verification, previous public-key continuity, app codesign and DMG
verification. Live appcast has build 75 and the exact signed archive URL.
[Public download receipt](artifacts/0610-release-029/download-verification.json).

Installed the verified public ZIP in Applications, keeping the previous app for
rollback. About visibly confirms 0.2.29 (75). Bundled CLI/MCP/skill files match
release source. The active campaign continued with the same detached worker and
saved plan through the UI restart; identifying operational details remain local.

Two immediate Sparkle UI checks reported 0.2.28 as newest despite independent
live-feed verification. Therefore installation used the verified public archive;
a successful automatic updater installation is not claimed. The app's durable
worker contract and detached process relationship were checked before quitting.

The active campaign holds the execution lease. The installed app bundles bridge
49; managed CLI/MCP/skills remain at bridge 48 until Studio automatically stages
the new files after active work finishes. No lease was bypassed, job cancelled,
model redownloaded or accepted plan rewritten.

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

Allow the normal deferred workflow refresh after active work finishes.
Already-connected MCP clients may need to reconnect to reload server guidance.
