---
entry: 0298
title: Release exact RFD3 motif selections
date: 2026-10-05
author: Codex
type: bugfix
status: complete
machine: Apple M4 Max, 40 GPU cores, 64 GB unified memory
---

## Context

User authorized patching and updating the app, MCP/CLI, GitHub and releases after
0293/0297 identified the still-installed broad RASA preservation bug. This release
contains that correction, not concurrent experimental lab-pool/UI development.

## What changed

Derived an immutable portable RFD3 runtime from c9fc19327d6b15b5a14b83b3d99c914e1dc52d2b2d1eb9e87b6cf0be49d27a3a.
Only the Foundry parser and bundled patch helper change; 36,894 other inventoried
files remain unchanged. New manifest:
780fa7ed3533e9b3a30ab4ceea0c6bd3c2c1f38b3e4b85d5a5ea01c6a485a4dc.
No model weights are in the archive. Old runtime retained; activation reused the
existing checkpoint/EMA assets. Normal motif centring remains fixed-target plus
selected motif; partial diffusion retains its existing real-coordinate semantics.

Engines detection inspects the actual imported Foundry source and reports Update
for the old selection patch. Tested old/new runtimes return update/ready correctly.
App0.2.23/build69/MCP41 (bridge1.15.1) catalog selects the corrected public runtime.
Native, CLI and MCP use this same managed runtime. Saved jobs retain pinned code.

## Validation and outcomes

- Candidate relocation imports passed, including a directory with spaces/Unicode.
- All14 real complete-preprocessing cases passed: translated inputs, scaffold
  lengths200/300, default/explicit origins, exact nine-atom motif masks, partial.
- Three patch tests, partial/dual-RMSD and motif-scoring contracts passed.
- Swift build and14 native tests passed;24 MCP planner/broker tests passed.
- One70-residue motif scaffold, SolubleMPNN derivative, Boltz complex and monomer
  validation completed through immutable MCP job8d956f496361.
- One13-residue source-peptide partial diffusion (1 Å, sequence preserved), Boltz
  complex and monomer validation completed through MCP job5696d892654f.
- Both use RFD3 200 steps/2 recycles/bf16, seed1, batch1. Prediction uses app Boltz
  25steps/3recycles. Generated backbone plus complex and monomer outputs have
  finite coordinates, required score tables and no nonadjacent CA pairs below2 Å
  (six structures total; adjacent residues of the same chain excluded).
- The actual motif job fixture has nine fixed unindexed atoms and705 fixed target
  atoms. Recorded sampler motif drift0; insertion RMSD1.709 Å. Its redesigned
  derivative fails normal complex/binder/motif-quality filters. Partial derivative
  passes configured filters. Neither outcome is an experimental binding claim.

No GPU work was active at the start: prior ordered queue and separate paired-SUMO
benchmark were complete. No existing jobs were paused or altered. Compilation and
archive creation overlap smoke work; no timing/performance claim is made.

## Reproduce and evidence

Validation/experiments/rfd3_motif_release_v1 contains package builder, locked
activation, public MCP smoke launcher, manifest and output auditor. Local raw
receipts/plans are in its output directory; compact public evidence is under
artifacts/0298-rfd3-motif-release. The archive is weight-free,396,216,075 bytes,
SHA256 e449e5e85ad2716186dfff7efaf475171a1a709ff5312c025900806c1ff02089.

## Limits and failures

No large-campaign quality/clash-rate comparison, fresh Mac, heterogeneous hardware,
or new motif-only centring mode. No model or relaxation changes. Initial harness
attempts corrected an inherited nonboolean DEBUG environment, an unapproved input
location (bundled fixture copied into the managed test workspace), a sandboxed
status/audit write and two mistaken test interpreter choices. Final checks use
managed environments; scientific jobs completed without errors.

## Publication

Published app v0.2.23-beta from87bd839 and update-feed commit e3d86d8 to main.
Published runtime runtimes-2026.10.05-1. All four GitHub app assets match local
SHA256/size; Studio's normal downloader successfully fetched and verified the
public runtime archive. This remains the existing ad-hoc signed trusted-beta
channel, with Sparkle EdDSA updates, not an Apple-notarized distribution.

Installed the exact released app at /Applications/iProteinStudio.app and reopened
it; prior app retained in build/app-backups. Installed/staged setup, catalog,
MCP41/bridge1.15.1 and RFD3 preparation scripts match the release. CLI doctor
passes and the active RFD3 manifest is the corrected780fa7 identity. No model
weights were downloaded. Publication and deployment JSON receipts are included.
No outstanding scientific job needs resuming.
