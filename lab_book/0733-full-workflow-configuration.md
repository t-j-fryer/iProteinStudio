---
entry: 0733
title: Show full workflow configuration and explain scheduling
date: 2026-11-04
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

## Context and changes
User requested only the full settings in configure mode. Backbone (RFD3/RFD4) and
Hunter now show all configuration fields without a Quick Setup selector. Hunter
prediction/advanced settings also appear directly. Prediction throughput help
explains concurrent workers versus sequential model reuse, memory tradeoffs and
engine defaults; removes the universal “measured optimum” claim. No defaults changed.

## Evidence and decision
Historical short-protein concurrency results are workload-specific (Lab0002).
Current ESMFold2/OpenFold use a resident worker; user overrides are still available.
Expose complete controls rather than retaining two overlapping form modes.

## Validation
Swift build and packaged beta/public-candidate builds passed; package code signing
verified by the build scripts. Existing workflow request, prediction-template
and RFD4 configuration harnesses passed. No new speed measurements. Interactive
GUI inspection of this presentation-only follow-up was not performed.

## Reproduce
`swift build`; `bash build_app.sh debug` in this public candidate worktree.

## Limits
No new scientific configuration or kernel promoted. No GPU rerun required for
these presentation-only changes. Public binary publication remains held pending
the existing release qualification.
