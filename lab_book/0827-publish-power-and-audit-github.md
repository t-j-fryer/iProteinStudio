---
entry: 0827
title: Publish power controls and audit GitHub synchronization
date: 2026-11-09
author: Codex
type: implementation
status: in-progress
machine: Apple M4 Max; offline/native UI and release qualification
tags: [ui, power, release, github]
---

## Context

User explicitly requests the shared power controls in the public release and asks
whether GitHub is up to date and merged. Promote the reviewed power-control patch
only. Preserve the paper baseline and unrelated private/uncommitted research.
No confidential molecule, workspace, scientific input or output is inspected.

## What was done

Transfer the qualified native power service, toolbar/settings/execution controls,
inert tests and documentation to the public candidate. Add non-mutating power
fixture tests to the default offline CI entry point. Public version0.2.40/build93;
CLI/MCP58 and scientific backend resources stay unchanged.

Audit refreshed both remotes: active private development and the public release
branch each matched their remote heads before promotion. No open PRs in either
repository. Back up the clean committed performance branch privately; do not
merge its separately scoped model/kernel changes into the release. Historical
local main and the public candidate tracking branch need fast-forward updates.
Uncommitted manuscript/Validation edits remain local. The paper-style pocket
viewer remains a private beta feature; it is outside this promotion.

## Results

Power fixtures, public Swift build and isolated native Automatic/High Power
panels pass. The complete local offline entry point passes69/69 commands,
including Swift tests and request/controller harnesses. Package and independent
public download/signature verification follow.
No new throughput measurement and no actual host power mutation.

GitHub's latest preexisting workflow run42673219919 failed before creating jobs.
Its public page annotation is: Internal server error, correlation
899e91a2-4a3f-4af8-8d2a-9a51c02c2b09. The workflow source is unchanged and Actions
permissions are enabled. The single retry successfully started jobs. The full local offline suite exposed
three integration issues: the new public power guide linked a private-only
benchmark entry; the desktop NESSO mock expected the old signature without the
optional geometry argument; and the standalone installer harness omitted its new
EngineRequirementIssue dependency. Corrected all three without changing pipeline behavior. The hosted retry also
exposed missing ripgrep, host-RAM-dependent fake queue tests on its7GB runner,
and two SwiftUI type-check timeouts. Install the explicit CI tool, pin CI Python
to the supported3.11.13 baseline, record explicit supported memory overrides
only inside inert queue fixtures, and split the two display strings into typed
parts. Production admission remains enforced by default; its dedicated rejection
and override tests are unchanged. The final hosted run must pass before release.

## Decision and rationale

Publish reviewed app functionality while keeping private development streams
separate. Use content/patch comparison for cherry-picked fixes; differing commit
histories do not imply the public fixes are absent. Do not merge all branches or
commit the dirty research tree merely to remove Git status differences.

## Reproduce

```bash
bash Tests/test_mac_power_mode.sh
bash Tests/test_mac_power_ui.sh /tmp/studio-public-power.png
python3 Tests/run.py
swift build --disable-sandbox
```

## Limits and what was not tested

Host settings remain untouched. The native administrator/write path has not been
live-exercised; generated scripts, cancellation/failure and readback are tested
with fixtures. Real hardware support falls back to Power Settings when unknown.
No new model inference, benchmark, other-Mac or engine installation test.

## Next

Complete release validation, publish signed artifacts/feed, install after any
necessary app restart approval, and report exact GitHub/CI/private-work status.
