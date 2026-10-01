---
entry: 0253
title: Automatically adopt predicted RFdiffusion3 targets
date: 2026-10-01
author: Codex
type: implementation
status: complete
---

## Context

Sequence-only users need to predict their target and use it directly in either
RFdiffusion3 or Protein Hunter RFdiffusion3 cycle00.

## Changes

Reuse the existing queued Target Prep engines and cache. Protein Hunter now adopts
the returned structure; RFdiffusion3 also automatically inspects chains and residue
ranges. Hotspots remain optional with a Use structure action. Re-predict now returns
to engine selection. Both controllers own a copy of their target before queueing,
with saved Target Prep configuration and content hashes when available.

## Validation

Swift build and all Swift request/controller/results contracts passed. The new
snapshot harness exercises both run layouts, exact content hashes, configuration
copying, cache deletion independence, external-path handling and malformed
metadata rejection. No new
scientific inference algorithm or GPU benchmark. Existing target prediction and
RFD3 stage paths were previously exercised; this change connects their UI handoff.

## Limits

No new GPU inference, fresh-Mac install, or complete engine matrix planned for this
UI/preparation change. Prediction remains a separately queued target-preparation
job; the design starts after the target is ready.

## Publication and local app

Released v0.2.19-beta / build65 from dadbbfd, update-feed commit42a190b.
Clean release compilation, packaged resource checks and code signature checks
passed. Published asset hashes, live feed build number and Sparkle ZIP signature
verified. The exact bundle is installed and open; prior build64 is retained.
Packaged UI inspection confirmed the new Protein Hunter button, engine choices
and optional Use structure action; original workspace settings were restored.
No GPU jobs were submitted, stopped or resumed by this follow-up. CPU compilation
can overlap ongoing benchmark host work; no throughput claim is made here.

MCP37 and the existing CLI target-prepare/structure-input contracts remain
compatible and unchanged. Concurrent ESM default changes were excluded from this
release. No model downloads or duplicate weights are introduced.
