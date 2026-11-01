---
entry: 0682
title: Isolate retained runtime metadata and retry release checks
date: 2026-11-01
author: Codex
type: bugfix
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
tags: [release, runtime, validation, rfd4]
---

## Context

The user authorized running pending GPU release validation after the Figure 2
benchmark finished, and requested context for the unfinished mixed protein–ligand
target feature. The deferred publication process stopped without publishing.
Ten framework checks failed before inference with changed runtime inventories;
the final two-length protein check completed. These are retained in the original
`Validation/output/studio_release_031_v1/` record.

## Cause and fix

The release qualification root was itself a retained runtime view. Child views
inherited its `assets.json` and `view.json` as symlinks; writing child metadata
therefore changed the parent and sibling inventories. The original provenance
guard correctly refused the queued requests. This was an orchestration defect,
not a failed model calculation or a reason to bypass integrity checks.

Exclude view metadata from inherited root files and require existing views to
have private metadata. A regression builds a parent and two child views, checks
independent inventories and unchanged parent bytes, and verifies that model-data
tampering is still rejected. The test failed before the fix and passed after it.
Preserve the old plans and failures; retry under fresh plans and output paths.
Reuse the completed length check only after receipt and exact-request checks.

## Validation

Runtime-view, runtime-binding and code-snapshot tests passed (six tests). Swift
builds and fresh GPU checks are recorded below as they complete. No performance
or scientific efficacy claim. New checks retain the normal planner, shared queue,
immutable code/runtime bindings, per-job sleep protection and model settings.

## Mixed-target context

The requested workflow has a binder, protein target and bound ligand. Current
protein search converts parents and prediction inputs to protein-only content.
An explicit rejection prevents ligand loss but does not implement the feature.
Dedicated ligand design and native annotated conditions are separate paths.
Documentation now explains this distinction. No mixed-target qualification is
claimed by the protein-only release checks.

## Next

Run the failed framework routes with the fixed isolation. Rebuild the candidate
artifacts before re-enabling deferred delivery; the original draft stays unpublished.
