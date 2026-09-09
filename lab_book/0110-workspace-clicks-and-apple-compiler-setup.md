---
entry: 0110
title: Fix workspace clicks and Apple compiler setup
date: 2026-09-08
author: Codex
type: bugfix
status: complete
machine: Apple Silicon local macOS developer machine; reported failure on user M1 MacBook Pro
tags: [ui, install, recovery]
---

## Context

The user requested single-click workspace switching and supplied
`/Users/thomasfryer/Downloads/setup-1788899983-8CB650CA.log` from an M1 MacBook Pro.
The log records NESSO/ESM downloads followed by a ProDy 2.4.1 source-build failure
in the mandatory sequence-designer environment: `fatal error: 'cmath' file not
found` in `prody/proteins/ccealign/ccealignmodule.cpp`. C extensions compiled;
the C++ extension could not find the standard library header. The log does not
establish the remote Mac's exact developer-tools installation or SDK selection.

## What was done

- Made the workspace icon/name/space an explicit plain navigation button beside
  its separate actions menu. Removed the row's double-click rename recognizer;
  Rename remains in the menu, context menu and detail header.
- Keyed detail-view identity by workspace UUID, resetting temporary inspectors
  and sheet state on selection. Bound all four workflow forms and the mode
  picker to the originating workspace UUID. Delayed callbacks no longer write
  into a newly selected workspace; updates to archived workspaces are ignored.
- Added a sourced Apple compiler helper, invoked before Python/model downloads.
  It resolves the selected macOS SDK, clang and clang++ through xcrun, exports
  explicit SDKROOT/CC/CXX and prepends the selected SDK's libc++ headers where
  present. Existing custom C++ include paths are retained after the SDK path.
- The helper compiles, links and executes an arm64 C++ program using cmath and
  vector, logs the selected tools, and fails with Command Line Tools recovery
  instructions. Detection and maintenance remain compiler-free. Studio does
  not change global developer-tools selection or substitute package versions.
- Added a ProDy/native-extension import to the staged sequence-designer runtime
  acceptance check. Ensure NHFAIL always begins a new line, including after
  package-manager output that omitted its final newline (seen in the user log).
- Documented workspace controls and setup retry/recovery. Added compiler tests
  and a packaging check for the new helper. Packaged local beta build 27.

## Results

No measurements — implementation only.

- Four compiler tests passed: real compile/link/run despite stale inherited
  SDKROOT; exported SDK headers/custom include preservation in a real compiler
  subprocess; failed compiler cleanup; actual installer failure before downloads
  with lock cleanup and successful compiler-free detection.
- Rebuilt cached ProDy 2.4.1 sources in an isolated temporary directory using
  the new helper and the existing managed Python 3.11 sequence-designer runtime.
  Imported ProDy 2.4.1 and its newly built `ccealign` extension from the temporary
  build directory. No installed packages or weights were changed. Build log:
  `/private/tmp/studio-prody-build27.ckvUgl/build.log`.
- Installer hardening and component contracts passed. The first hardening run
  could not see its test process under the sandbox; rerunning with process-list
  access passed. Workspace organization/navigation contracts passed after
  redirecting the restricted compiler cache into temporary storage.
- Final debug and release Swift builds passed. Content-addressed pipeline
  snapshot contracts passed with a writable temporary compiler cache.
- Packaged-resource checks and strict ad-hoc signature verification passed.
  ZIP/DMG SHA-256 checks and hdiutil verification passed. The read-only mounted
  DMG matched all 389 built-app entries (hashes, modes and symlinks), reported
  build 27, and was unmounted.
- Outputs: `build/iProteinStudio.app` and
  `build/unsigned-beta-0.2.0-27/iProteinStudio-0.2.0-unsigned-beta-apple-silicon.dmg`.
  This is a local dirty-tree beta, not a published release.

## Decision and rationale

Make navigation explicit and keep menu actions separate from the click target.
Persist edits against stable workspace identity instead of relying on global
selection during asynchronous work. Configure a matched Apple SDK/compiler and
check it before downloads rather than changing the pinned ProDy dependency or
treating a missing header as a failed model download. A genuinely incomplete
developer-tools installation still needs repair on the user's Mac.

## Reproduce

```bash
python3 Tests/test_apple_build_tools.py
bash Tests/test_installer_hardening_contract.sh
bash Tests/test_installer_component_contract.sh
CLANG_MODULE_CACHE_PATH=/private/tmp/studio-build27-module-cache bash Tests/test_workspace_organization.sh
swift build
release/release_app.sh --unsigned-beta --allow-dirty
```

## Limits and what was not tested

No fresh complete engine installation, neural inference, throughput claim or
model download. The isolated ProDy rebuild uses existing dependency packages,
not a fresh uv build-isolation environment. No access to the reporting M1 Mac;
an installation retry there is still required. Interactive GUI/VoiceOver
acceptance is unverified. No public release, Developer ID signing or notarization.

## Next

Retry Setup on the reporting M1 MacBook Pro; keep its new log if the compiler
preflight or a later installation stage fails.
