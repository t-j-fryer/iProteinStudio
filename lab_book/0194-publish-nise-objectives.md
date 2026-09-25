---
entry: 0194
title: Publish NISE objectives and cohort transfer
date: 2026-09-25
author: Codex
type: implementation
status: complete
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

All 57 fast-suite commands passed: 48 in the sandbox, and nine process/localhost
fixtures passed on targeted rerun with required system access. All 64 NISE tests
passed in the clean checkout, as did the release Swift build, eight XCTest cases
and executable Swift contract harnesses. A copied module cache was cleared after
its embedded source path prevented the first worktree build. No new model inference, benchmark, fresh-Mac install or
biological calibration. No model weights or campaign outputs are distributed.

## Local deployment

The current biotin campaign is active with retained code and two workers.
Do not stop or modify it. Shared workflow/MCP staging must respect its execution
lease; the updated app bundles MCP28 immediately, with shared staging deferred
until idle through the existing app refresh path.

## Published and installed

Published [0.2.7/build53](https://github.com/t-j-fryer/iProteinStudio/releases/tag/v0.2.7-beta),
MCP28, source commit 601d119; signed feed commit 775cf2b. Downloaded all four
release assets and matched sizes/hashes to local artifacts and GitHub metadata.
The live build53 feed archive signature verifies against the existing Keychain
identity. The DMG checksum, packaged resources and deep strict app signature pass.
All 235 source resource files match the downloaded app.

Installed the exact downloaded app at the existing local build/iProteinStudio.app
location, retaining build52 under build/previous-apps. The app is running and
its bundled doctor reports MCP28. Byte-for-byte signed-resource inventory is
unchanged after doctor execution; signature remains valid after GUI launch.
The original campaign PID84576 and resident PIDs3938/3968 remain unchanged.

Shared MCP remains24 while the active campaign holds the execution lease.
The running updated app uses its existing deferred staging path to install MCP28
and matching workflow resources when idle. Reconnect assistant MCP sessions
then. No campaign stop, setting change, resource-lock bypass or engine update.
The distribution retains the existing ad-hoc signed trusted-beta channel; it is
not Apple Developer ID notarized. Receiving-Mac and real Sparkle upgrade tests
remain unperformed. Receipts are local under build/release-verification-0194/ in
the release checkout, with deployment receipts in the canonical build directory.
