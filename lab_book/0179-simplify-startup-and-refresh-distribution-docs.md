---
entry: 0179
title: Simplify GPU startup and refresh distribution documentation
date: 2026-09-22
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, macOS 26.6.1
tags: [runtime, distribution, documentation, updates]
---

## Context

The user requested removal of routine shared-temp inspection, clarification of
GitHub/Sparkle delivery, and a repository-wide documentation cleanup. This
follows the recovery and inference evidence recorded in entry 0178. Fresh-Mac
qualification remains deferred by the user.

## What was done

Removed the GPU storage preflight from normal broker execution. The retained
module has an explicit `--diagnose` command for support only. It never enumerates,
clears or renames shared storage. A worker regression executes normal dispatch
with the diagnostic patched to fail if invoked. Existing bounded-child and
preservation fixtures remain.

Rewrote the README, install/update guides and experimental screening guide;
updated CLI, architecture, agent guidance, privacy/install wording, support,
results, runtime, testing and current Lab Book summaries. Preserved historical
records and compatibility identifiers. Moved four dated acceleration/distribution
proposals into `docs/research/`, retaining their evidence and updating references.
Added current documentation navigation and local-link checks. Added the existing
portable/runtime/PSICHIC fixture suites to the standard fast test command.

The full suite found a native Predict planning `UnboundLocalError`: branch-local
`sys` imports shadowed its use on the prediction path. Moved the import to module
scope. Updated stale fixture assumptions about developer source builds and
per-job runtime views; the code-update test now requires queued code preservation
while input-tampering tests continue to require refusal. The first source-build
fixture entered portable setup in its isolated temporary root; stopped it before
correcting the explicit source-build flag. No managed installation was changed.

Prepared app 0.2.3 build 46, MCP contract 24. Engine archive catalog, models,
scientific settings and precision are unchanged.

## Results

No new inference benchmarks — software and documentation changes only.
`python3 Tests/run.py`: **52/52 commands passed**, including seven GPU-storage
fixtures, ten inert engine-batch fixtures, eighteen native-job fixtures, portable
runtime/recovery tests, six XCTest cases and executable Swift contracts. Two
optional dependency-specific resident fixtures report skips in the standard
Python environment; no model inference is implied. `swift build` passed.
The current-guide check verified **118 local targets across 28 guides**.
Initial failures and their corrections are described above; full logs are kept
locally under `build/release-verification-0179/`.

Published [v0.2.3-beta](https://github.com/t-j-fryer/iProteinStudio/releases/tag/v0.2.3-beta),
build 46 from source `3b44fcc`; feed commit `62b2802`. Downloaded all four public
assets and matched their bytes, SHA-256 and GitHub asset digests to the local
release. Verified the downloaded ZIP's Sparkle EdDSA signature and live appcast
build/version/URL/length. The previous build 45 retains the same bundle ID,
HTTPS feed and public key, so it is eligible to discover build 46.

Installed that exact downloaded ZIP into the local build location after checking
its code signature, preserving the previous app. Staged app-owned resources with
a dated backup under the shared execution lock; no active/queued managed jobs
were present. All **324** source-to-app/managed pipeline file comparisons passed.
Managed `studioctl.py doctor` reports **ok, bridge 24** using control Python
3.11.13; installed-component detection ended `NHDONE|ok`. Existing model/runtime
archives remain unchanged. Relaunch is needed for already-running app/client
processes to load updated code.

Full verification receipt: local `build/release-verification-0179/RELEASE_VERIFICATION.json`.
The source sync retains unrelated canonical working files and merges user-only
Lab Book entries rather than discarding them.

## Decision and rationale

Shared macOS storage belongs to the operating system and may be used by other
apps. Checking it on every job adds a failure path without preventing recurrence
of the underlying OS problem. Keep explicit diagnosis separate from normal
execution. Do not introduce automatic shared-cache deletion or modify model
settings to mask an operating-system failure.

GitHub hosts immutable app/runtime assets. Sparkle reads the signed-archive
appcast; source publication alone is not an app update. Preserve the existing
update key, feed and bundle identifier so earlier distribution builds remain
eligible. Runtime packages keep their separate catalog and retained job bindings.

## Reproduce

```bash
python3 Tests/run.py
swift build
bash release/release_app.sh --publish-unsigned-beta
```

Publication requires the maintainer's existing Keychain signing key and GitHub
credentials. The script requires clean committed source and creates a new tag.

## Limits and what was not tested

No new scientific inference, fresh-Mac installation, older Apple-chip or older-OS
qualification, interactive VoiceOver, or actual in-app Sparkle replacement was
performed for this change. Signature/feed/asset verification is not a substitute
for those acceptance tests. No claim that the original OS scratch-storage fault
cannot recur. Historical local `Validation/output/` links intentionally refer to
ignored artifacts, not files downloadable from the GitHub source tree.

## Next

Complete clean-Mac installation and real older-build-to-newer-build Sparkle
acceptance on a separate test Mac before broad distribution.
