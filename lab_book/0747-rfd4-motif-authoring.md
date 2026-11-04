---
entry: 0747
title: Expose native motif selection and enable optimized kernels
date: 2026-11-04
author: Codex
type: implementation
status: completed
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

## Changes

The RFD4 motif form accepts an ordinary PDB/CIF, or the existing queued sequence
prediction route. The native-parser inventory drives residue picking and explicit
atom checkboxes, with amber coordinate-atom spheres and Clear all. Controls expose
absolute/relative geometry, fixed residue identity, indexed/unindexed placement,
contiguous groups and prefix/linker/suffix length bounds. Typed selections compile
through pinned upstream condition-spec authoring; no replacement scientific model.
Native annotated CIFs remain the route for multi-chain or non-protein motifs.

App, CLI and MCP54 share the typed request. Source fingerprints reject edited
inputs; missing/ambiguous atoms and conflicting settings fail explicitly. New
requests default optimized_kernels=true; saved explicit false stays false. No
extra reference inference was reintroduced. Version0.2.33/build82 is prepared as
beta and a local public candidate, not published in this task.

## Verification

Pinned native CPU authoring and tensor preparation passed absolute coordinates,
relative geometry, unindexed groups, variable lengths and backbone-only sequence
redesign. Missing atoms and changed inspected-source fingerprints were rejected.
The combined T4 lysozyme fixture (A10/A11/A20, 12 backbone atoms) produced23 tokens
within its21–27 range, exactly12 relative-coordinate atoms, three fixed sequence
residues and index groups of2+1. Inspection found164 residues and the preview IDs
matched the native inventory. Manifest and immutable outputs are recorded in
Validation0366. These are input/feature tests, not model-cycle qualification.

The actual WebKit/3Dmol harness passed exact atom overlays, residue-click binding,
loading a saved selection and clearing. Packaged-beta manual inspection loaded
2LZM, selected all eight atoms of A10, blocked sidechain sequence redesign, applied
the selection and confirmed the default kernel checkbox is on. Source prediction
reuses the existing TargetPredictor; no new prediction was launched here.

The public offline suite passed all68 groups (the final Swift group passed on
rerun). Both Swift builds and packaged resource comparisons passed. A concise
record is in artifacts/0747-motif-authoring/validation.json; detailed maintainer
logs are retained in the private beta checkout. Initial test invocations lacked required
runtime/import settings; reruns used the test fixtures correctly. The first full
Swift-contract run overlapped a final source text edit and was rerun after freezing
source. The original inspection test exposed an inherited DEBUG environment value;
the helper now explicitly uses the same native import environment as authoring.

## Kernel evidence and limitations

Default-on follows the user's explicit request and existing paired qualification:
Lab0741/0743 and Validation0358/0360 record50 matched Chain B pairs and the exact
T4 pair without automatic reference inference, on this M4 Max. No new timing or
biological-accuracy claim is made here.

The HA campaign owns the GPU and NESSO is already queued. Neither job was paused,
modified or resumed by this task. No new GPU motif inference, motif-retention or
functional efficacy campaign, other-Mac testing, VoiceOver, notarization, live
sequence prediction, or public publication was performed. Private research and
model weights are excluded from the public candidate.

Final acceptance: all six additional native input regression tests passed, including
all eight frameworks, weighted framework inputs, ligand conditions and length
allocation. Beta0.2.33-dev/build82 was installed and reopened; the previous beta
bundle is retained locally for rollback. The installed stable app remains0.2.32.
The public0.2.33/build82 candidate is built locally and has not been published.
