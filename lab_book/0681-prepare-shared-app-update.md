---
entry: 0681
title: Prepare shared app, CLI and MCP update
date: 2026-11-01
author: Codex
type: implementation
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [release, rfd4, ui, mcp, cli]
---

## Context

The user explicitly requested updating the installed public and private beta apps,
README, CLI, MCP and GitHub releases after Lab Book 0679. Public publication is
authorized for reviewed generic changes only. The preserved 0.2.30 baseline and
private beta research remain separate. The user requested that the active Figure 2
benchmark finish before any GPU release qualification; it must not be interrupted.

## Work in progress

- Shared docs and MCP guidance describe length allocation, all eight frameworks,
  automatic CDR boundaries, explicit predictor identities and saved hit filters.
- Added MCP/CLI saved-filter reporting and hit-only filtering with exact retained scope; the regression checks pass/fail/unknown verdicts and tampered receipts.
- Corrected stale development-only wording and distinguished search feedback from
  independent hit validation.
- Added job-scoped caffeinate to new typed RFD4 commands. Existing job commands,
  frozen code, settings and outputs are unchanged.
- Prepared version 0.2.31/build77, bridge51. Publication remains gated on tests.
- Validation0327 defines bounded GPU checks through the normal immutable planner
  and shared job queue. No new inference is launched outside the broker.

## Validation

Previous CPU feature authoring passed eight frameworks and three lengths (0679).
Full offline contracts, build/package and GPU results will be recorded here as
completed. No new speed, accuracy or memory claim is made.

## Limits

Mixed protein–ligand target refinement remains unsupported. Expanded predictor
and framework combinations require the pending end-to-end checks before public
release. No model runtime/checkpoint update is intended. No fresh physical Mac,
wet-lab qualification or generalized design performance claim.

Native visual review was attempted twice; the computer-use service reported “Sky Computer Use native pipe startup failed”. No UI action or launch was completed through that service.

## Completed offline checks

- All67 standard offline command groups passed, including14 Swift XCTest cases,
  standalone Swift contracts and the public app build.
- All20 focused RFD4 backend tests passed.
- The new saved-filter result-view regression passed separately; it was added
  to the fast-suite entry point after the above suite had started.
- All24 MCP tests passed. An initial sandboxed rerun could not read host memory;
  the normal host run passed without changing scientific settings.
- All228 local documentation links across44 current guides passed.
- Local beta0.2.31-dev/build77 packaged and passed strict deep signature checks.
- The native visual-review service remained unavailable.

Reviewed the public candidate diff including its previously prepared live-results
fix. The added structures contain only the existing public catalogue's apo
frameworks. No model weights, private peptide workflows, manuscript results or
new machine-specific paths are included in the public changes.

## GPU acceptance and publication

All 11 queued release checks completed; 12 generated starts and 22 refold predictions passed the retained-output audit. The published release contains RELEASE_QUALIFICATION.json. This is bounded software acceptance, not an efficacy claim. Artifact source: c4f53d9c77f69c8265b71274fdc6d51b68822b0e. Local delivery status is recorded separately.
