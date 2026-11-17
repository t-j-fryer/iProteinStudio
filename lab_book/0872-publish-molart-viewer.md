---
entry: 0872
title: Publish simplified Molart viewer
date: 2026-11-17
author: Codex
type: port
status: in-progress
machine: Apple M4 Max, macOS
tags: [ui, viewer, molart, release]
---

## Context

The user explicitly requested public GitHub/release and local delivery of the
qualified Beta104 Molart viewer and simplified menus. Public0.2.44/build102
predates this feature. Promote only the generic viewer changes from63593a90
and42f7fb02, excluding private research, workflow experiments and beta records.

## What was done

Prepare public0.2.45/build105. Image style has Illustration, Paper pocket and
one Molart choice; Chain style selects its21 upstream presets. Routine style
prose/counts/parser notes are absent from the controls. Notices and licence
texts remain bundled. Update README, documentation and changelog.

Molart is pinned at a200691c2432fcb005ae2206352891b74847e64b; Three.js0.187.0
is bundled offline. The reproducible build tools, hashes and native renderer
harness accompany the source. Scientific adapters, bridge61/server1.21.1,
workflow generation2026111302 and client-neutral operating skill are unchanged.
No model weights or private experimental code are promoted.

## Results

Native offline Molart acceptance passed all21 upstream styles, simple menus,
PDB/mmCIF, PNG export, camera handlers, per-chain styling, trajectory scrubbing,
renderer disposal and source preservation. Existing Paper pocket native
regression also passed. `swift build` passed; documentation links passed265
targets across53 guides. All73/73 fast regression commands passed. Signed ZIP/DMG checksums, DMG
verification and independent CryptoKit Ed25519 verification passed. The public
release/tag points to51bfb5e16def13d9be89ab42939a58f785c8d24b; actual public
downloads are byte-identical, and the extracted app passes strict codesign and
resource checks. GitHub CI44161206595 remains queued without a runner; prior
main CI failure was hosted-runner capacity, not a test failure.
No performance measurements. See [qualification](artifacts/0872-molart-public/qualification.json).

## Decision and rationale

Port the tested renderer and narrow lifecycle/input adapter rather than
reimplementing upstream illustration geometry. Keep protein-only Molart
separate from the ligand/picking/cone capabilities of Illustration/Paper pocket.
Use Science mode by default; Art changes only the drawing and is explicit.

## Reproduce

```bash
swift build
python3 Tests/run.py
bash Tests/test_molart_viewer.sh build/release-audit-0.2.45/molart
bash release/release_app.sh --unsigned-beta
```

## Limits and what was not tested

Native acceptance uses bundled T4 lysozyme and synthetic display fixtures.
Pointer drags are DOM-dispatched with a test-only pointer-capture shim; these
exercise upstream camera handlers, not physical trackpad/native mouse events.
No private workspace or molecule is inspected. No GPU inference, new biological
validation, performance benchmark, cross-Mac renderer survey or pipeline settings
change. Molart does not display ligands, nucleic acids, picking or cones.
Distribution remains ad-hoc signed and Sparkle EdDSA verified, not Apple notarized.

## Next

Public source, release archives and update feed are published. Running public
app restart approval is pending; Beta104 already carries identical renderer code
and its installed signature/resources pass. Monitor queued GitHub macOS CI.
