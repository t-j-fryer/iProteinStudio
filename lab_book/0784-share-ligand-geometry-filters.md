---
entry: 0784
title: Share ligand geometry hit filters and interactive views
date: 2026-11-06
author: Codex
type: implementation
status: complete
machine: Apple Silicon development Mac; CPU and native WebKit checks only
tags: [ligand, geometry, ui, mcp, cli]
---

## Context

User requested the Figure 4 contact/linker geometry method as an optional hit
filter throughout small-molecule binder design, its cone display in the app,
and molecule rotation/zoom. Follow Lab0772's exact Figure4f/4h policy audit.

## What was done

Shared `ligand_geometry_policy.py` and CPU `ligand_geometry.py` wrap the existing
unchanged `nise/atom_geometry.py`, `biotin_exit.py`, and `linker_geometry.py`.
Policy atom indices use exact input SMILES; predictor/source maps are explicit.
The app's preset selects the same nine free-biotin core atoms at 6Å, plus the
existing open/restricted exit gate; other molecules use selected contact/SASA.
Source graph, symmetry, stereochemistry, receipt and structure hashes are checked.

Optional app/CLI/MCP56 policy for Protein Hunter, RFD3, RFD4, NISE and retained
single-ligand RFD4 motifs. NISE checks advancement; other routes keep objectives
and add completed-output geometry verdicts. Apo results do not inherit a holo
pose; motif aggregate verdicts additionally require requested holo geometry.
Dedicated NESSO/PSICHIC verification and final NISE refolds receive the same gate.
Result readers AND geometry with saved gates and fail missing/invalid evidence.
Raw structures and scores are not rewritten. CPU work stays within the existing
job/lease and retained code/runtime; no new scientific launcher or package install.

Shared 2D/3D atom picker, deterministic input-order RDKit display conformer,
3Dmol rotation/zoom/pan/reset, preserved labels/roles and input-order selections.
Sampled cones replay recorded nominal torsions at actual coordinates; count
agreement is required. Existing NISE receipts can be rendered read-only.

## Results

No performance measurements. Five real-CPU tests pass, including the two saved
Figure4 poses: original exit labels and nominal sample counts match; input-order
presets map to the same nine atoms across SMILES traversals. Altered structures,
results and missing requested receipts fail; disabled gates preserve prior verdicts.
Read-only legacy receipt replay calls no classifier. Native ethanol authoring,
real CPU RFD4 featurization and exact authored atom mapping pass.

Existing regressions: 5 exit, 11 NISE request/checkpoint, 24 MCP bridge, 15 ligand
screening tests pass. Full RFD4 suite: 79 tests run; 78 passed initially and one
packaging import needed `tools` on PYTHONPATH, after which all seven tests in
that module passed. An initial Boltz-interpreter invocation lacked AtomWorks;
this was an environment error, not native qualification, and was replaced by the
pinned RFD4 invocation. Swift request/migration/results and geometry AND-gate
harnesses pass; native atom selection/highlight tests, correct directed-bond picking after 2D zoom/rotation/reset, and real WebGL drag,
zoom/reset tests pass. Cone rendering inspected in native WebKit with the paper
fixture. These are CPU/UI checks, not a fresh GPU end-to-end workflow run.

Local beta is 0.2.35-dev/build84, MCP56. Installed in Applications with the previous beta retained for rollback; opened in the real app and verified 3D controls, optional gate controls and Start blocking for an empty enabled gate. Restored the gate to off; no job submitted. All29 changed/new bundled resource files match source; no model weights are packaged. Public source candidate is prepared
separately; no public tag, release upload, appcast or installed stable replacement
is authorized by this preparation. Sanitized `qualification.json` records scope;
private test logs remain under the corresponding artifact folder.

## Decision and rationale

Retain the exact published classifier instead of generalising its amide model
to arbitrary linkers. Generic molecules use explicit contact/SASA requirements;
only free biotin exposes the paper's exit preset. Atom conditioning is not an
acceptance check. No new model inference is needed to replay saved geometry.

## Reproduce

```bash
NANOHUNTER_ROOT="$HOME/.iproteinstudio" bash Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh --detect
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" -B -m unittest discover -s Tests -p test_ligand_geometry.py -v
STUDIO_SWIFT_CASES=rfd4_configuration,nise,workflow_requests,iterative,results python3 Tests/run_swift_contracts.py
CLANG_MODULE_CACHE_PATH=/tmp/studio-geometry-clang-cache SWIFT_MODULECACHE_PATH=/tmp/studio-geometry-swift-cache swift build --disable-sandbox
```

## Limits and what was not tested

No fresh neural-model/GPU run, new hardware/runtime, binding assay or performance
benchmark. Source classifiers remain byte-identical to Figure4 policy code.
Recorded paper structures are private replay fixtures, not redistributed in the
public tests. AME-41 enzyme beta is a distinct benchmark workflow, outside the
small-molecule binder forms; this change does not add arbitrary linker chemistry
to that benchmark. Multi-ligand geometry needs explicit per-instance policy and
is blocked rather than choosing a ligand silently.

## Next

Beta0.2.35-dev(84) installed and open. Matching0.2.35/build84 public candidate
built in the release worktree;24MCP regressions, shared Swift contracts and four
public CPU tests pass (one private-coordinate replay explicitly skipped).
All69public changes reviewed:51source files match beta byte-for-byte; the
pre-existing private/public scope differences in result models/viewers are
preserved. No research files, model weights, private backlog or beta controls
were transferred. Packaged metadata, resource parity and no-weight audit pass.
Public publication remains a separate explicit release step.
