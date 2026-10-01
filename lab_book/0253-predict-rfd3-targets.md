---
entry: 0253
title: Automatically adopt predicted RFdiffusion3 targets
date: 2026-10-01
author: Codex
type: implementation
status: validated
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
