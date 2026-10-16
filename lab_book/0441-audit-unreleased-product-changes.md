---
entry: 0441
title: Audit unreleased app and bridge changes
date: 2026-10-16
author: Codex
type: audit
status: complete
machine: local Mac; read-only source and installed-package inspection
tags: [release, app, mcp, cli, audit]
---

## Context

User requested an inventory of edits since the last GitHub/app/MCP/CLI update.
This is a release-gap audit, not authorization inferred to publish all local work.

## What was done

Read GitHub commits/releases through the connected GitHub API, local version and
changelog, tracked diffs, untracked production modules, installed app Info.plist,
and SHA-256 hashes of selected bundled/managed adapter files. Reviewed recorded
validation in entries 0291, 0296, 0322–0324, 0422–0423 and 0430–0434.

## Results

- Remote latest commit and local HEAD: 25b3eb92dae59b4f4e48f3f10f7d6b8607faeb3d,
  2026-10-05. No newer commits on the queried default branch.
- Latest published release in the releases collection: v0.2.23-beta,
  2026-10-05T15:58:55Z. The releases/latest endpoint returned 404 because the
  current releases are prereleases; the collection supplied the actual answer.
- Installed /Applications/iProteinStudio.app: 0.2.23, build 69.
- Source, installed app and managed runtime all still declare MCP_VERSION 41;
  that number does not establish source equality.
- 75 tracked files were modified before this audit entry, plus untracked source,
  tests, documentation and research artifacts. No exhaustive release manifest
  was built and no raw research data was staged.
- For nanohunter_run.sh, mcp/server.py, broker.py, hunter_stages.py and
  resident_predictor.py, installed app and managed runtime match each other but
  differ from current source. New prediction_output_reporting.py,
  nise/optimization_transfer.py and pool/service.py are absent from both installed
  copies. This is a selected-file comparison, not a full binary/source audit.

Unreleased source groups: shared epitope generation/refinement policy and residue
validation; frozen prediction-profile propagation and zero-recycle handling;
batched CPU reporting/cached coordinate inspection; MCP RCSB integration,
engine/framework composition, candidate exports and broker cancellation locking;
experimental lab-pool UI/CLI and NISE optimization transfer; revised region-mode
UI/artwork and documentation/tests. Entries 0291 and 0296 predate the last release
but explicitly remained local work, so dates alone do not determine inclusion.

Already released: resident OpenFold/CPU MPNN (0.2.21), ESMFold2 Full 3/50 (0.2.20),
separate Hunter initialization/refinement (0.2.18), simplified NISE/native region
controls (0.2.22), exact RFD3 motif atom selection/runtime repair (0.2.23).

Recent biotin affinity 50-step/one-sample, resident LASErMPNN and CPU overlap
qualifications are experiment-specific, not blanket product defaults. Their
limits and measured results remain in 0430–0434. Manuscript/benchmark artifacts
require a separate public-data/provenance review before inclusion.

## Decision and rationale

Recommend a scoped product release of reviewed fixes and selected mature bridge
features. Keep lab-pool/prototype capabilities explicitly experimental and do not
silently promote experimental scientific budgets. Update version/provenance and
validate the assembled package before deployment/publication. Preserve running
jobs' immutable runtime snapshots.

## Reproduce

Compare git status/diff and VERSION/CHANGELOG; GET GitHub commits?per_page=1 and
releases?per_page=3 for t-j-fryer/iProteinStudio; inspect installed Info.plist and
hash matching relative pipeline files under source, app Resources and managed root.

## Limits and what was not tested

No fresh build, regression tests, GPU inference, GUI interaction, packaged install,
remote-client acceptance or performance measurement in this audit. Historical test
results are evidence about their recorded source versions, not qualification of
the entire present working tree. No app/runtime/job changes, commits, pushes or
release uploads were performed.

## Next

Prepare a reviewed release manifest, run relevant regression/build/portable-package
checks, resolve experimental-feature scope, and deploy consistently to app/MCP/CLI.
