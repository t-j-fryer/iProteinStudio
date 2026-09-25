---
entry: 0190
title: Publish job progress and recovery
date: 2026-09-25
author: Codex
type: implementation
status: complete
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

Keep the updated app open for automatic shared-resource staging after the active campaign finishes, then reconnect existing MCP clients. Fresh-Mac/full-engine acceptance remains separate.

## Post-download correction

0.2.5/build48/MCP26 was published and its four downloaded assets, EdDSA signature,
feed and 234 resource files verified. A subsequent signature recheck after the
bundled doctor command detected new `__pycache__` files inside the extracted app.
This exposed an existing native-broker packaging problem: its writable signed
resource directory was not protected against Python's default cache writes.
The local app was not replaced. Published archives remain immutable.

Prepare corrective 0.2.6/build49/MCP27: suppress bytecode at every bridge entry
point before local imports, and add `-B` to the native broker invocation. Add
real subprocess coverage of CLI, stdio MCP and the other bridge entry points,
verifying byte-for-byte resource inventories after use. Verify the new extracted
app's signature both before and after its bundled bridge smoke check.

The corrective entry-point test passed for all five executable bridge scripts;
18 MCP integration tests and 11 recovery tests passed again. `swift build` passed.
The test invokes actual scripts with bytecode-related environment variables
removed and compares complete before/after file inventories, not just syntax.

## Final publication and local deployment

Published [0.2.6/build49](https://github.com/t-j-fryer/iProteinStudio/releases/tag/v0.2.6-beta),
**MCP27**, source `32f0eb6`, signed-feed commit `c6fc695`. Marked the 0.2.5 release
as superseded without replacing its immutable assets. Downloaded all four 0.2.6
assets and matched each SHA-256/size to both local artifacts and GitHub metadata.
The live feed points to build49 and its EdDSA ZIP signature verifies with the
unchanged project key. All **234** packaged resource files match source. The
extracted app's code signature verifies before and after its bundled MCP doctor
command, with no bytecode caches created. Packaged-resource checks passed.

Installed that exact downloaded app at the existing local `build/iProteinStudio.app`
location; the old build46 bundle is retained under `build/previous-apps`. App
launch succeeded. The installed broker's doctor reports MCP27; bounded log reading
returned 500 lines, and a read-only recovery check correctly declined to clean up
the older live worker. Code-signature verification still passes after app/bridge
use. The existing managed campaign stayed running with the same worker PID.
No actual cleanup, stop, resume, scientific settings or runtime migration occurred.

**Deferred local shared staging:** the active campaign holds the execution lease,
so the installed shared MCP remains24. The app's existing deferred-refresh path
will stage its MCP27/workflow resources after jobs finish while the app stays open
(or on a subsequent idle launch). Existing assistant sessions must reconnect
then. No bypass of the execution lock was used. Bundled native broker/viewer use
MCP27 immediately; frozen older jobs keep their original logging/worker code.

Receipts (local, not shipped): `build/release-verification-0190/LOCAL_DEPLOYMENT.json`
and `INSTALLED_SMOKE.json`; downloaded-asset receipt and logs under the release
checkout's `build/release-verification-0190-0.2.6/`. The live GUI displayed the
standard Applications-folder notice. Further native UI navigation could not be
verified because the computer-use pipe closed; the earlier isolated viewer render
and this installed CLI/service smoke remain the UI's recorded acceptance scope.
An actual Sparkle installation on another Mac and full-engine inference were not
performed. The canonical workspace synchronization preserves unrelated edits.
