---
entry: 0684
title: Preserve molecular context through protein-target design
date: 2026-11-01
author: Codex
type: implementation
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

## Context

User explicitly requested mixed protein–ligand target support, including preserved chemistry, atom identities, every prediction and complete-assembly checks. This is a shared public/beta feature. Release delivery is held until qualification; existing frozen scientific jobs are unchanged.

## What was done

Implementing explicit source-graph manifests, native RFD4 conditioning, ligand-bearing prediction inputs, complete-assembly exports, mapped atom identities and separate geometry verdicts. Protein and antibody inverse folders retain their established roles; no ligand-aware sequence-design claim. Noncovalent small-molecule context is the scope; bonded polymer–ligand assemblies and nucleic acids are not implicitly approximated.

## Validation

See Validation entry0331 and experiments/rfd4_mixed_target_v1. CPU authoring, chemical round trips, missing-entity negative checks, predictor input conventions and small managed end-to-end jobs required before release. No performance or affinity claim.

## Limits and what was not tested

CPU implementation checks complete; no completed mixed-target GPU qualification yet. Existing release qualification checks protein-only routes and cannot qualify this change.

## Checks completed

-31 RFD4 tests passed, including eight framework and multichain/length CPU feature audits. Targeted updates additionally passed9configuration tests,6mixed-chemistry/assembly tests and the complete-assembly result/export test.
-37 MCP tests passed with isolated synthetic workloads. Corrected the composition test fixture to declare its synthetic memory workload; production memory admission is unchanged.
-`swift build` passed in beta and public release worktree.
-Protein/biotin and nanobody/biotin native CPU feature qualification passed. Managed GPU smoke jobs are queued behind the user's new Figure2 native-sequence benchmark; that run is unchanged.
-Found and corrected IntelliFold result collection using its actual saved native filenames. Existing release failures are retained; follow-up checks are required.

## Release status

The shared patch is present in `.worktrees/paper-release` and beta. Installed apps and the draft GitHub release are not yet promoted. The previous delivery watcher is stopped; completing mixed-target GPU qualification is an additional delivery requirement.
