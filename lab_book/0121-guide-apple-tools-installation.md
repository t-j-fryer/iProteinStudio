---
entry: 0121
title: Guide Apple Command Line Tools installation in the app
date: 2026-09-09
author: Codex
type: bugfix
status: complete
machine: local Apple Silicon development Mac; Command Line Tools installed
tags: [install, ui, tests, packaging]
---

## Context

A new user hit the instruction to run `xcode-select --install` in Terminal.
The compiler probe introduced in entry 0110 detected missing/broken tools, but its
failure message contradicted onboarding's no-Terminal promise. No new remote
installer log was supplied, so this is a fix to the confirmed prerequisite flow,
not a diagnosis of every possible compiler failure on that person's Mac.

## What was done

- Added a passive `xcode-select --print-path` check before `xcrun`, avoiding an
  implicit Apple installer prompt before Studio can explain the prerequisite.
  The existing real C++ compile/link/run check remains authoritative.
- Added the structured `NHREQUIRES|apple-build-tools` marker and actionable setup
  failure text. Detection and maintenance paths remain compiler-free.
- Added shared Setup/Engines guidance with **Install Apple Tools**, **Open Software
  Update**, **Retry Setup** and log access. The Install action executes the system
  `/usr/bin/xcode-select --install` directly and leaves Apple's installation and
  authorization UI to the user. No Terminal window or shell command entry is needed.
- A successful installer request is not considered a completed tools installation.
  Retry is explicit, keeps the originally reviewed setup arguments, reacquires
  the execution lease, and reruns compiler validation before engine downloads.
  Repeated clicks are guarded while the request is pending. Failed installer
  requests retain guidance and log Apple's response.
- Documented first-use behavior and added regression tests. Bumped app build to 33.

## Results

No measurements — implementation only. Six compiler/installer Python tests passed,
including real C++ execution, broken/missing compiler fixtures, no implicit Apple
installer request, maintenance detection and recovery. Debug `swift build` passed.
The real native controller passed the mocked-process harness: explicit installer
launch, duplicate-click guards, failed requests, no premature completion, exact
argument preservation across retries and execution-lease release. The standalone
harness was corrected to use a writable
module cache and include the existing IntelliFold enum test stub before passing.

Release build 0.2.0 (33), deep/strict app signature verification and the packaged
resource contract passed. The bundled setup script and Apple tools helper match
source bytes. App, ZIP and DMG were created under `build/`; they are local unsigned
beta test artifacts, with no GitHub release/appcast publication. `git diff --check`
passed. Artifact:
`build/unsigned-beta-0.2.0-33/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`.
ZIP and DMG SHA-256 verification and the DMG internal checksum verification passed.

## Decision and rationale

Keep Apple's tools as an explicit prerequisite because existing pinned engines
build native dependencies. Open Apple's official installer rather than bundling
Apple SDKs or silently changing the machine's developer-directory configuration.
Keep retry explicit rather than assuming `xcode-select --install` exit 0 means the
download and installation have finished. Preserve selected engine arguments across
the prerequisite interruption instead of reconstructing them from an edited form.

Apple's documented installation flow:
https://developer.apple.com/documentation/xcode/installing-the-command-line-tools

## Reproduce

```bash
python3 Tests/test_apple_build_tools.py
bash Tests/test_apple_build_tools_ui.sh
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules swift build --disable-sandbox --skip-update
bash release/release_app.sh --unsigned-beta --allow-dirty
```

## Limits and what was not tested

No actual Apple tools installation, clean-Mac/second-Mac acceptance, interactive
Apple dialog or Software Update navigation was performed on this already configured
host. Native controller tests intercept only the external process boundary; they
do not install engines or show system dialogs. No full science suite or model
inference was rerun. Existing design jobs and their runtime snapshots were left
alone. Missing full Xcode/XCTest on this development host is separate from the
Command Line Tools prerequisite needed by installed engines.

## Next

Test build 33 on the affected Mac. If the compiler still fails after Apple's tools
update, inspect its log for
SDK selection or other compiler problems. GitHub release publication remains
separate from producing the local app/DMG.
