---
entry: 0442
title: Release integrated workflow fixes and ligand efficiency
date: 2026-10-16
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40 GPU cores, 64 GB unified memory
tags: [release, lasermpnn, affinity, scheduling, mcp]
---

## Context

User authorized updating app/MCP/CLI/GitHub/releases with the inventory in 0441,
explicitly excluding the experimental lab compute pool and including the recent
resident LASErMPNN, reduced affinity budget and CPU/GPU overlap work.

## Changes

- Removed pool integration from native entrypoints and MCP; preserved excluded
  development sources locally under ignored build/release-preparation-0442.
- Shared Boltz profiles expose affinity_steps=50 and affinity_samples=1, with
  native CLI override precedence and app controls. Five affinity recycles and
  both native affinity heads are unchanged. Evidence: 0432, Validation0195.
- Shipping LASErMPNN wrapper uses the qualified cached native model with RNG
  reset after loading; native sampler and constraints retained. Protein Hunter
  owns one CPU worker, RFD3/NISE use at most two with one numerical thread each.
  Historical NISE ignored the sampling seed; new receipts identify seed policy v2.
- NISE Phase0 refinement and Phase1 prepare a bounded next chunk during independent per-input Boltz
  folding. Whole-stage selection and scorer shortlist barriers remain intact.
  Geometry acceptance remains at the original scientific stages.
- Retains audited epitope/settings/MCP/reporting work from 0441.

## Validation and deployment

Curated release-tree Swift build passed. The full CPU suite ran87 commands:86
passed; the sole failure was a documentation link to a local-only prototype.
That link was corrected and its test rerun successfully. Seven focused efficiency
tests also passed, including the portable RFD3 adapter path. The portable launcher
uses the snapshotted app overlay, without editing the immutable engine runtime.
The initial sandboxed test run could not inspect processes; rerun with proper
process-inspection access. Initial Swift sandbox cache failure likewise rerun.
Swift build passed in the normal Xcode environment. No performance claim from
this integration alone; previous benchmark scopes and limitations still apply.

## Limits

Publication pending assembled-package qualification. Existing accepted jobs must
retain their frozen sources/profiles. No model weights may be committed/shipped.


## Real-model qualification

Managed paired job918549fba5af used four saved biotin starts (two per generator),
two complete redesign/fold/affinity cycles, one proposal per parent and one resident
Boltz model. Both arms used two CPU slots; fresh-process sampling had a stage
barrier and resident sampling overlapped bounded preparation. All8 sequences,
P(bind) values, geometry verdicts,0.80-gate decisions and per-cycle rankings match.
Audited fold/affinity replay emitted no new model requests.

The original EXACT check failed7/8 PDB hashes. This failure remains in immutable
raw outputs and job state. A separate, explicitly retrospective numerical audit
found maximum atomic displacement0.008832Å, maximum all-atom displacement RMS
0.000631Å, maximum ligand-pLDDT difference0.00875/100 and score difference0.0000875.
It passes declared numerical thresholds RMS0.005Å/max0.05Å/score0.001 with exact
sequences, P(bind), decisions and rankings. This is numerical equivalence, NOT
bitwise identity; exceptionally close ties can differ. CPU regression activity
coincided with this smoke, so its159.59/158.71s arm timings are not a speed claim.

Managed CPU jobf8caf7ce6e24 completed64 warm calls/128 sampled sequences, all
FASTA sequences and scores exactly equal to the fresh seeded call. RSS ranged
817–913MiB; measured late growth51.8MiB stayed below the predeclared128MiB bound.
An intentionally interrupted owned CPU worker failed its request, and a new
worker reproduced the fresh output. This short soak does not establish multi-day
memory stability. Qualification evidence is in artifacts/0442-ligand-efficiency-release.

Both qualification plans preserve runtime, input and code identities. Subsequent
source-only changes correct the portable RFD3 launcher and CPU-policy metadata;
those paths have executed contract/migration tests. The live benchmark was
cancelled through Studio with user authorization; its frozen settings and completed
outputs remain unchanged and it will be resumed after deployment.


## Publication and deployment

Published v0.2.24-beta/build70 from4f45c6c; update feed commitc26f896 on main.
All four published asset SHA256 digests and byte counts match local artifacts.
Release app/resource contracts and deep code-signature verification passed. This
continues the existing ad-hoc signed beta/Sparkle EdDSA channel; no claim of Apple
notarization. No weights are in the app or release assets.

Installed and opened the exact app at /Applications/iProteinStudio.app; previous
app retained under build/app-backups. Automatic staging refreshed MCP42/bridge1.17.0,
CLI, pipeline helpers and the portable RFD3 overlay; checked hashes match the app.
CLI doctor passes. No model or engine runtime download/reinstallation occurred.
Existing MCP clients may need reconnecting to discover the new tool schema.
The biotin benchmark was resumed via the same job159313e82b33 and unchanged plan
159313e82b33136a549317b9c78888369a89130ca848bd6c94ebae4f9c83b826.
