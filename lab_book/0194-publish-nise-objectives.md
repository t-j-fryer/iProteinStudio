---
entry: 0194
title: Publish NISE objectives and cohort transfer
date: 2026-09-25
author: Codex
type: implementation
status: in-progress
machine: Apple-silicon development Mac; no inference benchmark
tags: [release, nise, mcp]
---

## Context and work

User requested local app, MCP, GitHub and release updates following entries
0191–0193. Prepare 0.2.7/build53/MCP28 from a clean linked checkout, excluding
unrelated analysis changes. Preserve the trusted-beta signing channel and key.
Include the explicit resident-pool continuation compatibility already used by
this NISE work; do not silently change default worker counts.

Add cohort, objective and pool tests to the science fixture test entry point.
Use native SwiftPM build selection to avoid the local Xcode build-engine issue.
Release receipts remain local under build/release-verification-0194/.

## Validation and limits

Verification pending. No new model inference, benchmark, fresh-Mac install or
biological calibration. No model weights or campaign outputs are distributed.

## Local deployment

The current biotin campaign is active with retained code and two workers.
Do not stop or modify it. Shared workflow/MCP staging must respect its execution
lease; the updated app bundles MCP28 immediately, with shared staging deferred
until idle through the existing app refresh path.
