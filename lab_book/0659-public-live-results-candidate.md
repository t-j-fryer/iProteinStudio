---
entry: 0659
title: Prepare the public live results viewer fix
date: 2026-10-29
author: Codex
type: bugfix
status: complete
machine: Apple M4 Max, 64 GB unified memory, macOS 26.6.1
tags: [ui, results, rfd4, release]
---

## Context

The user requested the general live-results update in the upcoming public release,
with results-viewer and file-management inspections added to its local to-do list.
The current released app must remain protected while the candidate is prepared.

## What was done

Created a local `release/paper-next` worktree at `.worktrees/paper-release` from
`release/paper-0.2.30` (dd4163b). Transferred only the general UI changes:

- Direct live-results entry points in job queue, job progress and activity.
- Supported jobs can open their results without matching a registered workspace.
- RFD4 opens the shared refreshing results browser before the campaign ends.
- Generated backbones and family/candidate counts are labelled independently of
  optimisation cycles; unknown custom experiment formats are not guessed.
- Added executable routing checks for the supported job kinds and an unsupported
  benchmark kind. Existing loader tests retain incomplete/stale-output handling.

Added `PUBLIC_RELEASE_TODO.md` with results-viewer inspection and file-management
inspection left pending. No experimental peptide adapter, chemistry metrics,
private campaign source, beta installer controls or model weights were copied.

## Validation

- `swift build --build-system native -c debug -j 4` passed in this worktree.
- `python3 Tests/run_swift_contracts.py` passed the full executable contract suite,
  including new unregistered-workspace routing checks and existing incremental
  result loading, partial-write exclusion, sample identity and RFD4 contracts.
- The first new routing fixture compared URL directory formatting rather than
  path identity; corrected the fixture and reran the full suite successfully.
- `git diff --check` passed; reviewed the complete source diff against dd4163b.
  No runtime/backend source or scientific settings changed.
- The exact public candidate was not installed or tested interactively. Its
  general UI behaviour was previously exercised in Beta (Lab Book 0658); this
  candidate's evidence is the build and executable contracts above.

## Delivery and limits

Local candidate only. No public push, tag, appcast, release upload, installed-app
replacement, model inference or active-job changes. A full file-management audit
and broader viewer inspection remain to-do items, not claimed completed work.
