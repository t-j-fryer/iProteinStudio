---
entry: 0684
title: Preserve molecular context through protein-target design
date: 2026-11-01
author: Codex
type: implementation
status: completed
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

## Context

User explicitly requested mixed protein–ligand target support, including preserved chemistry, atom identities, every prediction and complete-assembly checks. This is a shared public/beta feature. Release delivery is held until qualification; existing frozen scientific jobs are unchanged.

## What was done

Implemented explicit source-graph manifests, native RFD4 conditioning, ligand-bearing prediction inputs, complete-assembly exports, mapped atom identities and separate geometry verdicts. Protein and antibody inverse folders retain their established roles; no ligand-aware sequence-design claim. Noncovalent small-molecule context is the scope; bonded polymer–ligand assemblies and nucleic acids are not implicitly approximated.

## Validation

See Validation entry0331 and experiments/rfd4_mixed_target_v1. CPU authoring, chemical round trips, missing-entity negative checks, predictor input conventions and small managed end-to-end jobs required before release. No performance or affinity claim.

## Limits and what was not tested

Technical qualification is complete for the bounded cohort below. Covalent assemblies, nucleic-acid context, broad chemical coverage, binding efficacy and cross-Mac behavior were not tested. Native UI inspection was unavailable because the computer-use service failed to start.

## Checks completed

-31 RFD4 tests passed, including eight framework and multichain/length CPU feature audits. Targeted updates additionally passed9configuration tests,6mixed-chemistry/assembly tests and the complete-assembly result/export test.
-37 MCP tests passed with isolated synthetic workloads. Corrected the composition test fixture to declare its synthetic memory workload; production memory admission is unchanged.
-`swift build` passed in beta and public release worktree.
-Protein/biotin and nanobody/biotin native CPU feature qualification passed. Managed GPU smoke jobs are queued behind the user's new Figure2 native-sequence benchmark; that run is unchanged.
-Found and corrected IntelliFold result collection using its actual saved native filenames. Existing release failures are retained; follow-up checks are required.

## Release status

The shared patch is present in public and beta. Version 0.2.31 was published after all qualification audits passed. Installed-app delivery is recorded separately; previous draft artifacts and superseded test jobs remain retained.

## GPU integration findings and corrections

The first IntelliFold mixed assembly completed two cycles and retained all ligand atoms. Its existing annotation incorrectly included ligand chains in the global ipSAE minimum. Corrected the shared IntelliFold scorer to use the input YAML's protein identities and verified token counts. Mixed-target search also explicitly scopes its exported confidence and reward to protein pairs. Raw predictions and native confidence remain preserved.

The 600M check failed before inference because its isolated environment does not contain Gemmi. Chemistry normalization/checks now execute as CPU-only operations in the already pinned RFD4 preparation runtime, rather than changing predictor environments. A real call from the ESMFold2 environment passed. Added collision-free ligand chain mapping for temporary MPNN PDB inputs and saved the mapping.

Superseded only the still-queued mixed-target tests; retained completed/failed outputs. The corrected twelve-condition cohort uses fresh immutable plans (`qualified2`). Other release checks continue unchanged. No new manuscript job was interrupted.

OpenFold3's resident writer generated structures but discarded its already computed PAE, leaving protein design without ipSAE. Added an instance-local output callback to retain native PAE/token mapping and annotate only protein pairs. No model, settings or inference arithmetic changed. Two CPU regressions passed, including the real upstream callback with multiple samples. Fresh mixed and protein-only managed checks are required; the failed prediction and cancelled pending check remain retained.

Corrected a native-preflight regression: generated nanobody placeholders must not be reinterpreted as experimental ligand chemistry. Native authoring already audits the source; explicit annotated inputs omit only generated binder placeholders before strict per-ligand sanitization. Real protein-only and biotin-bearing annotated fixtures passed, along with ten mixed tests, the37-test MCP suite and both Swift builds.

Native nanobody generation completed, but AbMPNN failed while writing the combined protein/ligand PDB: RFD4 uses NaN B factors for unscored generated atoms, making ProDy compare an AtomGroup unequal to itself. Normalize only nonfinite B factors in the temporary MPNN input to zero, with an explicit atom-level record; retain original CIF/confidence unchanged. The exact failed fixture reproduced the error, and the corrected copy passed ProDy concatenation with all13 MPNN input feature fields exactly equal and all16 ligand atoms retained. Eleven mixed tests and both Swift builds passed. Native nanobody generation is reused from its verified receipt; supersede only the queued protein check.

## Final technical acceptance

The corrected twelve-condition mixed-target cohort completed and passed the read-only identity, protein-only score and geometry-gating audit. This covers two native generation/refinement routes and ten predictor profiles, with two predictions per route. A geometry rejection remains a rejection; technical acceptance does not require an efficacy hit. Earlier failed/superseded jobs remain retained. RELEASE_QUALIFICATION.json contains each verdict. The public release was published from c4f53d9c77f69c8265b71274fdc6d51b68822b0e; installed-app delivery is recorded separately.

## Acceptance summary

- Eleven general release routes passed: 22 refold predictions covering the selected ten predictor profiles, eight catalogue frameworks and two lengths.
- Twelve mixed-target routes passed the technical audit: 24 predictions, including native protein generation and audited native nanobody generation reused for its corrected refinement. All predictions retain the complete ligand atom inventory and protein-only score scope.
- Seventeen assemblies passed the geometry gate; seven failed it and remained rejected. This is an integrity check, not a measured binding success rate.
- Eleven mixed CPU regressions, the real ProDy feature-equivalence check, OpenFold native-writer tests, resident-resume/MCP checks, both Swift builds, bundle signatures and artifact hashes passed.
- Binary source: `c4f53d9c77f69c8265b71274fdc6d51b68822b0e`. Public release includes `RELEASE_QUALIFICATION.json`. No weights or predictor environments were changed.
