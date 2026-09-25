---
entry: 0190
title: Publish job progress and recovery
date: 2026-09-25
author: Codex
type: implementation
status: in-progress
machine: Apple Silicon development Mac; software fixtures and packaging
tags: [release, mcp, progress, recovery]
---

## Context

The user requested packaging, local app/MCP deployment and GitHub publication of
[engine progress](0188-add-engine-progress-logging.md) and the
[job viewer and recovery](0189-add-job-progress-viewer-and-recovery.md).

## What was done

Prepare 0.2.5/build48/MCP26 in a clean linked checkout. Include only the reviewed
progress/recovery changes; preserve unrelated workspace changes. Add recovery
and progress tests to the standard fast suite. Retain the existing trusted-beta
channel, bundle identifier and Sparkle signing key. Engine archives, weights and
scientific settings are unchanged.

## Results

All **56/56 fast-suite commands passed** in the clean release checkout, including
14 observer tests, 11 recovery tests, 20 desktop-job cases, eight XCTest cases
and executable native contract harnesses. Optional dependency-specific fixtures
retain their explicit skips in the generic environment. No scientific benchmarks.
Publication and downloaded-artifact verification follow this source commit.

A predeployment check found the existing managed campaign still alive and holding
the execution lease. The app bundle can update safely; shared managed workflow/MCP
staging must wait for that job to finish. The app's bundled broker supports the
viewer immediately, without rewriting the active job's retained code.

## Decision and rationale

Publish a new immutable version with a signed update feed rather than replacing
existing release assets. Preserve active jobs and their recorded runtime/code.
Local staging must respect the execution lease.

## Reproduce

```bash
python3 Tests/run.py
swift build
bash release/release_app.sh --publish-unsigned-beta
```

## Limits and what was not tested

No full-engine inference, student-Mac reproduction, fresh-Mac install or actual
Sparkle old-to-new installation on another Mac. This update improves observation
and safe recovery; it does not establish the original calibration stall's cause.
The distribution remains ad-hoc signed, not Apple Developer ID notarized.

## Next

Complete tests, publication, archive/feed verification and safe local deployment.
