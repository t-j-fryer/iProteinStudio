---
entry: 0144
title: Complete XCTest validation after Xcode installation
date: 2026-09-17
author: Codex
type: audit
status: complete
machine: Apple Silicon development Mac; Xcode 27.0 (27A266a)
tags: [testing, xcode, nise]
---

## Context

Build-38 verification in [0143](0143-biotin-launch-and-update.md) could not run
XCTest with Command Line Tools alone. The user installed Xcode, completed its
licence/first-launch setup, then requested continuation.

## What was done

Confirmed `/Applications/Xcode.app/Contents/Developer` is selected and
`xcodebuild -checkFirstLaunchStatus` succeeds. Ran the blocked `swift test` suite
and a fresh `swift build`; full logs are in `artifacts/0144-xcode-test-validation/`.
No app or engine source/settings changed.

Also inspected the blocked campaign through managed job_status and
results_overview, then read its recorded candidate rejections. No further
inference or filter changes were made.

## Results

All **six XCTest tests pass**, with zero failures; the app build passes with the
new toolchain. This resolves the missing-framework limitation in 0143. The
separate Swift Testing runner's zero-test footer is expected because this target
uses XCTest; six XCTest cases were executed.

The biotin pilot stopped in first refinement: five of six candidates failed
terminal-oxygen exposure checks. The remaining candidate passed geometry but
scored 0.7088484786, below the configured 0.80 early gate. No lineage advanced;
cycle-2 noising/repair acceptance remains untested. Affinity was correctly omitted
for the five geometry failures. See the saved
[rejection summary](artifacts/0144-xcode-test-validation/pilot_rejections.json).

## Decision and rationale

Keep reviewed scientific filters unchanged and retain the guarded hold on the
full campaign. Recorded candidate attrition is separate from the resolved XCTest
installation issue. Build 38 needs no new distribution solely because its
development test framework became available.

## Reproduce

```bash
xcodebuild -checkFirstLaunchStatus
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules \
  swift test --disable-sandbox --skip-update
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules \
  swift build --disable-sandbox --skip-update
```

## Limits and what was not tested

No new inference, new pilot seed, scientific filter relaxation, GUI interaction
tests or new DMG. Existing pilot data was inspected read-only. No scientific
efficacy or throughput claim.

## Next

The full campaign remains held until a bounded pilot passes branch acceptance.
Any subsequent pilot must retain these failed attempts and separately record its
request and random seed.
