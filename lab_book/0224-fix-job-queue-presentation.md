---
entry: 0224
title: Center the Jobs panel and make dismissal explicit
date: 2026-09-29
author: Codex
type: bugfix
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [ui, queue, release]
---

## Context

The user reports Jobs extending toward the screen edge and leaving the app
shaded after Escape. Native inspection reproduced the large right-edge toolbar
popover over a dimmed workspace. The current Protein Hunter test job is active;
the biotin job remains paused per0223.

## What was done

Moved Jobs presentation from the dynamic toolbar button's popover to a centered
workspace sheet. JobQueueView has an explicit Done button with Escape shortcut.
Show run dismisses the sheet before navigating. Nested progress/log details
remain independently dismissible. Release0.2.15/build61; MCP remains35.

## Results

`swift build` passes. No measurements — UI behavior fix only. Package and native
open/close checks are recorded below after completion.

## Decision and rationale

A large scrollable queue with nested job details needs a stable presentation
host and an explicit close control. Use standard sheet lifecycle/dimming rather
than manual opacity changes or coordinate offsets on an edge-anchored popover.
No job cancellation, resumption, scientific setting or engine code changes.

## Reproduce

Open Jobs from the toolbar. Check that the whole panel stays within the window,
close with Done, reopen and close with Escape, and inspect progress/logs before
returning to the queue. Show run should navigate and close the queue. Verify
the workspace becomes usable without residual shading after dismissal.

## Limits and what was not tested

No fresh Mac, multiple-display matrix or scientific inference qualification.
Existing managed jobs continue through app UI replacement. No bulk cleanup is
needed for this UI issue. Biotin must remain stopped until the user requests it.

## Next

Verify the packaged UI, install and publish the follow-up release.
