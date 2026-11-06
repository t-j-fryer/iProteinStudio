---
entry: 0787
title: Map geometry selections through native Boltz standardization
date: 2026-11-06
author: Codex
type: bugfix
status: in-progress
machine: Apple Silicon development Mac; CPU regression tests only
tags: [ligand, geometry, mcp, cli, privacy]
---

## Context

User supplied a geometry-preflight chemical-state mismatch traceback and explicitly
required diagnosis without inspecting the confidential molecule. Only source and
the pinned engine parser implementation were inspected. No reported run directory,
input molecule, saved user output, app workspace contents or screenshots were read.
All new regression fixtures are declared synthetic molecules in the test source.

## What was done

Reproduced the same error in0.2.36 using synthetic acetate. The geometry form uses
input-SMILES indices, while native Boltz affinity preprocessing can standardize the
chemical state. Exact-state matching previously rejected that native transform.

Trace labelled input atoms through the pinned Boltz standardizer. Require its
unlabelled result to equal the actual scoring molecule and check parser hash,
complete one-to-one labels, elements/isotopes, bond connectivity, specified atom
and bond stereochemistry. Match the resulting exact graph to the scoring atom
manifest; symmetry-equivalent mappings must preserve each selected set. No relaxed
substructure matching or independent chemistry standardizer is introduced.
Non-Boltz chemical-state mismatches still fail. Mapping-limit exhaustion fails.

Record the mapping, native parser hash, equivalent-match count and state-change
flag in geometry receipts. Explain native standardization in the shared form.
Expected CLI validation failures return a concise message rather than a traceback.
App, CLI and MCP57 share the correction; version0.2.37/build87. Existing accepted
jobs retain frozen helpers, code and runtimes; retry with a new plan/run.

## Results

Seven new real-CPU regression tests pass, including charge-state changes and
canonical atom reordering, native parser/output mismatch rejection, symmetry,
lost atom labels/connectivity/atom and bond stereochemistry, real holo geometry
measurement with source preservation, receipt reuse and actual CLI subprocesses.
Four existing public geometry tests pass; the private-coordinate replay is
explicitly skipped. All24 MCP regressions pass. Public Swift build and beta87
build pass. No neural inference or performance measurement.

## Decision and rationale

Respect the predictor's native preprocessing while proving atom correspondence.
Simply removing the exact-state guard or using neutralized/relaxed matching would
lose the proof of which atom each requirement addresses. Atom conditions and
geometry acceptance criteria remain separate. The Figure4 classifiers are unchanged.

## Reproduce

Run only declared synthetic/public fixtures; do not read the user's inputs:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 "$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" -B -m unittest discover -s Tests -p test_ligand_geometry_standardization.py -v
bash Tests/test_mcp_bridge.sh
swift build --disable-sandbox
bash release/build_local_beta.sh
```

## Limits and what was not tested

The confidential molecule/job was deliberately not inspected or rerun, so its
exact transformation is unknown. No GPU campaign, other-hardware test, new parser
version or new chemistry method. Native transformations that lose atom identity,
connectivity, isotope or specified stereochemistry remain blocked. No broader
ligand compatibility or binding-activity claim.

## Delivery

Published `v0.2.37-beta` from clean commit
`ee8188d6cd55e0a0da48adf9233eea008fea0dfd`. The live build87 feed, downloaded
assets and independent Ed25519 verification pass. All four changed bundle
resources match source; no model weights. Actual preflight from the downloaded
package passes with synthetic glycine. Both public/beta resource contracts pass.

The user explicitly approved both app restarts with workspace inspection excluded.
Computer Use refused lifecycle input without a fresh app-state snapshot; none
was captured. Asked for explicit permission to use macOS quit/open commands
instead, preserving the requested no-inspection boundary. Installation is pending
that mechanism choice. No user project or molecule has been read.
