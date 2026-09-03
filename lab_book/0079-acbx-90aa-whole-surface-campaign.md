---
entry: 0079
title: Test 90-residue whole-surface minibinders against alpha-cobratoxin
date: 2026-09-03
author: gpt-5-codex
type: experiment
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, mlx, acbx, surface-scan, solublempnn, boltz, resident-worker]
---

## Question

Can the corrected EMA RFdiffusion3 MLX pipeline generate 100 fixed-length
90-residue minibinder backbones against experimental alpha-cobratoxin without
an epitope definition, then validate two SolubleMPNN sequences per backbone by
resident Boltz complex and binder-alone prediction?

## Immutable plan

- Plan: `plan-ffe1d820b2b9ae20`
- Plan SHA-256:
  `ffe1d820b2b9ae20bc4ac9cd261a0e529e75f42769336142d8d4f378f1b7ec8a`
- Job: `job-ffe1d820b2b9`
- Campaign:
  `~/.iproteinstudio/projects/untitled_design/rfd3_runs/acbx_1ctx_surface_90aa_100`
- Target: corrected experimental RCSB 1CTX, chain B, 71 residues, 541 input
  atoms, ten SG atoms and five disulfides.
- RFD3: verified EMA weights, 100 backbones, exactly 90 binder residues,
  200 timesteps, two recycles, BF16, batch size four, two queues, seed zero.
- Placement: `surface_scan`, no hotspot or atom conditions. The small target
  produced ten nonredundant surface origins, with ten designs per origin.
- Sequence design: SolubleMPNN, two sequences per backbone, temperature 0.1.
- Validation: all 200 candidates (`top_n=200`), resident Boltz holo and apo.
- Saved strict filters: iPTM >= 0.5, ipSAE(min) >= 0.5, binder pLDDT >= 0.8,
  target-aligned pose RMSD <= 2.5 Angstrom and apo-vs-holo binder RMSD <= 2.0
  Angstrom.

## Initial acceptance

Fixture generation completed in 89 seconds. The first surface origin produced
ten checkpointed backbones. All ten contained exactly 90 binder C-alpha atoms,
100% valid adjacent C-alpha geometry, the complete 540-atom Foundry target
representation, ten SG atoms and the five expected disulfides. Their radius of
gyration ranged from 11.715 to 13.222 Angstrom. Direct all-heavy-atom checking
of the first eight found no sub-2-Angstrom inter-chain contact in seven; one had
a single borderline 1.987-Angstrom contact and must not be silently treated as
clash-free.

## Current state

The detached, caffeinated, checkpointed campaign is running in the backbone
stage. Final backbone distributions, sequence counts, resident-worker timings,
Boltz metrics and hit verdicts do not yet exist and are not claimed here.

## Reproduce/status

```bash
/usr/bin/python3 "$HOME/.iproteinstudio/mcp/studioctl.py" \
  job-status job-ffe1d820b2b9
```

## Limits

- Only the first of ten surface origins has completed at this checkpoint.
- The campaign has not yet reached SolubleMPNN or Boltz.
- The M4 Max timings above are measurements on this machine only.

