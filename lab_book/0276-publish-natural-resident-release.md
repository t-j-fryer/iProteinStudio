---
entry: 0276
title: Publish natural workspace and resident OpenFold release
date: 2026-10-02
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

## Context and scope
Publish the native identity/navigation from entries 0268, 0270 and 0271 and
app-wide resident OpenFold/CPU MPNN from 0272. Version 0.2.21, build 67, MCP 39.
Shared CLI adapters and the MCP planner carry the same execution policy. Existing
portable environments and weights are reused. Website art provenance is bundled;
this release does not change the separate website's audience or deployment.

## Work and evidence
The Figure3 coordinator job-465040f858d2 was paused through the broker after the
80-aa Boltz HK1 refinement cohort completed. Queue HOLD protects its ordered
citrate and retrospective successors during compiler/package work. Immutable
campaign snapshots and raw predictions are retained.

Swift build and all 14 Swift tests passed, including first-launch routing.
An initial unit invocation used system Python without PyYAML; tests were rerun
with the installed OpenFold runtime. Packaged asset checks now compare required
artwork and the icon with source. Core science evidence remains the real six-wave,
12-structure OpenFold acceptance, same-effective-seed replay and exact CPU MPNN
sequence equality recorded in 0272; these are not rerun for a branding release.
No end-to-end OpenFold speed factor is claimed.

## Reproduce
Run swift build, swift test, Tests/test_openfold_resident.py using the OpenFold
Python environment, test_rfd3_predictor_scheduling.py, test_hunter_stages.py,
test_mcp_bridge.py and test_iterative_cli_contract.sh. Build/publish from a clean
checkout using release/release_app.sh --publish-unsigned-beta; the existing
Sparkle EdDSA key signs the update archive. Apple notarization is not claimed.

## Limits
No fresh-Mac install, older macOS/VoiceOver audit, or long memory soak in this
release check. Native UI review and its coverage limitations are recorded in
0268/0270/0271. No model weights or private runtime packages enter Git.

## Delivery
Published v0.2.21-beta from clean source 5bca3b6; update-feed commit 8ce5151.
GitHub main and the live Sparkle feed advertise build 67. All four GitHub asset
SHA-256 digests match local files; the feed includes the EdDSA archive signature.
DMG SHA-256: 1e312ef1ec497ccab660952c77ab0c13096ae1355c70249199341d304bdb31ae.

Installed the exact release app at /Applications/iProteinStudio.app and reopened
it. Preserved the former build as build/iProteinStudio-build66-before67.app.
The installed CLI doctor reports MCP39, all profile/schema checks passed, and
hashes of the released OpenFold/MPNN/planner files match the managed installation.
Setup detection still reports existing engines installed; no environments or
weights were downloaded or duplicated. Native UI checked Design chooser opening,
all three method entries, artwork rendering and installed Engines status.

Release checks: 14 Swift tests; all Swift request/results harnesses; 5 OpenFold
receipt tests; 4 RFD scheduling; 10 Hunter stage; 23 MCP (also rerun from clean
checkout); CLI contract and packaged resource/signature checks passed. Updated
one stale CLI assertion that previously expected OpenFold residency to fail.

Broker resume requested for the same immutable Figure3 job after all builds;
ordered watcher restarted with the original manifest. Completed 80-aa Boltz HK1
refinement and all earlier audited cohorts remain on disk. Citrate and
retrospective follow in their existing order. Release maintenance time is not
part of an inference measurement. No fresh-Mac acceptance is claimed.
