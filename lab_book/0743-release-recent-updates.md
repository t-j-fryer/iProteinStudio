---
entry: 0743
title: Qualify and publish the accumulated Studio update
date: 2026-11-04
author: Codex
type: implementation
status: completed
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

## Context
Explicit authorization to pause NESSO, complete GPU acceptance and publish the
recent app, MCP, CLI and release changes. The old0.2.32 draft/build78 remains held;
new build81/MCP53 replaces it only after the current source passes acceptance.

## Fix and validation
RFD4 ESM ligand scoring incorrectly resolved Boltz-standardized atom identity in
an ESM-only environment. Use the existing ESMFold2 native atom-map helper, preserve
input chemistry, and coordinate ligand export/audits in the pinned RFD4 runtime
(which has Gemmi). The resident model still executes in its pinned ESM runtime.
No environment or weights are modified. NISE keeps its existing supplied manifest.
Native chemistry identity/export/routing and pinned600M receipt tests passed four cases. Direct ESM-only export
testing exposed the missing Gemmi dependency and motivated explicit controller
routing rather than changing the installed environment.

## Additional GPU-discovered repair

The initial600M run completed native prediction but failed strict receipt validation:
the shared adapter omitted `beta_assets` from the expected identity. It now calls
the existing pinned600M asset validator and matches the native writer exactly.
Full/Fast identity is unchanged. The failed job remains intact; a fresh frozen
600M run passed, including native atom export and selected-objective search.
No receipt check was weakened.

## Release plan
Validation0360, experiment studio_release_032_v2: six shared workflow routes plus
paired T4 optimized/standard generation and T4 prediction with/without templates.
Use existing Studio preparation, immutable plan/start, GPU lease, caffeinate,
runtime snapshots and accounting. Inspect complete public diff before publication.
Old failed outputs remain immutable. NESSO paused through supported job control;
resume the original job after release checks and shared-asset installation.

## Limits
Technical software acceptance, not biological efficacy or new speed measurements.
68 offline command groups passed; four targeted native-chemistry/receipt tests
passed; Swift builds and both build81 bundles passed. The public archive signature
was independently verified with CryptoKit against the bundled Sparkle public key.
The public diff was checked for weights, private experiments and machine paths
in shipped source. All ten GPU routes passed the final immutable-output audit. Public release
`v0.2.32-beta` is published with verified build81 artifacts and the qualification
JSON. Public and beta apps installed; CLI/MCP doctor reports bridge53. Original
NESSO resume is recorded separately below.

Source: public `e5100c2458ab93f61b76c7aca7aae9cea43cad1a`, private `84f8e75`.
Evidence: `Validation/output/studio_release_032_v2/` retains immutable preparation,
original and final job ledgers, both snapshots, source qualification and packaging
verification. Only `scripts/nise/esmfold_runtime.py` differs between the two frozen
science snapshots; the600M route uses the new snapshot. Other completed routes
retain their original provenance. No biological efficacy, new hardware qualification,
or new whole-workflow speed claim is made.

## Final acceptance

Eight RFD4 routes and two T4 predictions passed. The six search routes retained
16 scored predictions; the explicit standard/optimized T4 pair retained exactly
one120-aa design per arm with identical saved tensors and sequences. Both T4
predictions retained the requested164-aa sequence, one sample and the explicit
template state. The prior automatic reference folder was absent. These are
software acceptance counts, not independent binding validation.

The existing public distribution channel remains an ad-hoc-signed trusted beta,
with a verified Sparkle Ed25519 archive signature, not Apple notarization. Old
installed bundles are retained under the release output directory.

## Local delivery and NESSO recovery

Both public and beta app bundles installed and reopened at build81. Shared
CLI/MCP assets staged through the app execution lease; doctor passed at bridge53
and installed Python files matched the packaged source. NESSO
`job-e0d6fb15dfc2` resumed through supported job control and reports running under
its original plan digest
`e0d6fb15dfc2f2922bcce781ac1a610990da3e9eef5d4799df088c9d1859dd4d`.
Existing job snapshots and engine environments were preserved.
