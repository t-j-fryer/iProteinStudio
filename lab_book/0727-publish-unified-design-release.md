---
entry: 0727
title: Qualify and publish unified design release
date: 2026-11-03
author: Codex
type: implementation
status: completed
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [release, rfd4, mcp, cli]
---

## Context

The user explicitly requested publication to the public repository, app, CLI,
MCP and releases following 0719 and 0726. Version 0.2.32/build78/bridge52 retains
the existing Sparkle-signed trusted-beta channel. Publication is held until the
bounded new-route acceptance checks pass; private research stays excluded.

## Work

Public diff review found omitted sibling ligand helpers in retained workflows.
Capture now includes the shipped sibling resources; GUI snapshots contain them
before hashing. Direct source CPU preparation resolves only shipped helpers,
never a weaker installed fallback. A retained-code regression verifies this.

Validation0355 declares six bounded routes using the established 0.2.31 release
preparer, immutable plans, runtime/code snapshots, shared queue and job-scoped
caffeinate. Existing jobs and models remain unchanged. Normal offline checks,
public-source review, packaging and delivery verification are in progress.

## Limits

No efficacy or speed claim. Each newly exposed ligand predictor and weighted
framework/conformer route requires the output audit. No public push or release
upload has yet occurred in this entry.

## Offline acceptance

All 68 standard offline command groups passed, including Swift build/tests and
request/result harnesses. The focused RFD4 suite passed 30 tests; snapshot/design
checks passed 13 tests. The strengthened native snapshot contract passed, and
the public WebKit molecule harness passed exact-centre placement, five roles,
multiple roles, resizing and clearing. Release-gate fixtures passed.

The initial ligand preflight correctly rejected conformer files outside managed
imports. The two owned fixtures were copied into this qualification project's
inputs and fresh plans use those paths. The failed preparation remains retained;
no import policy was expanded and no raw settings were rewritten.

GPU checks wait behind the active prediction campaign in the existing queue.
The retained delivery gate will publish only after all six checks and the output
audit pass, with source/artifact hashes, clean public tree and unchanged remote
main rechecked. Installation additionally waits for idle jobs and closed installed
apps, preserves backups, and rejects an independently changed installation.

## Final delivery follow-up

The original failed acceptance attempt remains intact. Validation0360 and Lab
Book0743 record the corrected source and all ten passing final routes. Published
`v0.2.32-beta`, build81 / MCP53, from `e5100c2458ab93f61b76c7aca7aae9cea43cad1a`.
The earlier build78 draft was replaced only after the new acceptance passed.
