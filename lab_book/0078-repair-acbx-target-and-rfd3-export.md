---
entry: 0078
title: Repair the aCbx target and RFdiffusion3 target export
date: 2026-09-03
author: gpt-5-codex
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, mlx, acbx, target-structure, disulfide, boltz, mcp]
---

## Context

The raw RFdiffusion3 complexes made the alpha-cobratoxin (aCbx) target look
grossly malformed, while template-free Boltz re-predictions of the same designed
sequences showed a recognizable toxin fold. The immediate question was whether
RFD3 was moving the fixed target and whether Boltz should receive a target
template. This followed the EMA and surface-placement repairs in
[[0076-enforce-rfd3-ema-weight-provenance]] and
[[0077-add-explicit-protein-surface-origin-modes]].

## What was done

- Compared every target C-alpha in the earlier raw RFD3 outputs with the saved
  input. The target was preserved exactly up to the one rigid translation used
  by the fixture: aligned C-alpha RMSD was 0.000000 Angstrom.
- Found that the MLX writer filtered generic Foundry atom14 names (`V0` through
  `V8`) before converting them back to residue-specific names. It therefore
  emitted N/CA/C/O/CB only for the fixed target, deleting every deeper side-chain
  atom including all cysteine SG atoms. The writer now maps the atom14 slot back
  to the real atom name first.
- Traced the bundled aCbx asset separately. It was not an experimental
  three-finger-toxin structure: its all-residue C-alpha RMSD to RCSB 1CTX was
  11.777 Angstrom and only four sulfur pairs were in disulfide range. Replaced it
  with the complete 2.8-Angstrom X-ray structure from RCSB PDB 1CTX chain A,
  remapped to Studio target chain B. The exact 71-residue sequence matches the
  shipped example.
- Added a fail-closed example integrity test for sequence identity, 541 atoms,
  ten SG atoms, the five expected disulfides and the default whole-surface mode.
- Changed example staging from first-copy-wins to an atomic refresh. Existing
  installations now receive corrected bundled scientific assets; user projects
  remain untouched.
- Reclassified legacy B67/B69/B71 as an execution-acceptance selection rather
  than a validated epitope. The RFD3 worked example now starts with whole-surface
  placement.
- Staged the corrected exporter through the built app and ran a new five-backbone
  aCbx campaign through immutable MCP plan `plan-b402e93db0002574`, SolubleMPNN,
  resident Boltz complex prediction and resident Boltz binder-alone prediction.
- Started the requested matched 100-backbone mNeonGreen campaign as immutable
  MCP plan `plan-eb1ed631a657c25e`. It was cancelled at the user's request after
  ten backbone checkpoints; no completed campaign statistics are claimed.

## Results

The corrected aCbx source asset has SHA-256
`fbca4a6431e89f15967ae373dcc6811152a23aae3f12c2f00591fd26e56ead41`.
The completed smoke campaign is at
`~/.iproteinstudio/projects/untitled_design/rfd3_runs/acbx_1ctx_surface_ema_smoke5`.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| old bundled target vs experimental 1CTX | 71 C-alpha | aligned RMSD | 11.777 A |
| old bundled target | 10 SG | sulfur pairs <2.3 A | 4 |
| experimental 1CTX replacement | 10 SG | expected sulfur pairs <2.3 A | 5/5 |
| old MLX raw target export | 1 output | target atoms retained | 351 |
| corrected MLX raw target export | 5 outputs | target atoms retained | 540/541 each |
| corrected MLX raw target export | 5 outputs | SG atoms / correct disulfides | 10 / 5 each |
| corrected MLX raw target export | 5 outputs | target C-alpha RMSD | 0.000000 A each |
| corrected aCbx RFD3 backbones | 5 | valid adjacent C-alpha geometry | 100% each |
| corrected aCbx sequence designs | 10 | iPTM, median / maximum | 0.755 / 0.902 |
| corrected aCbx sequence designs | 10 | ipSAE(min), median / maximum | 0.278 / 0.660 |
| corrected aCbx sequence designs | 10 | binder pLDDT, median / maximum | 0.811 / 0.915 |
| corrected aCbx sequence designs | 10 | bound-pose RMSD, minimum / median | 13.699 / 23.495 A |
| corrected aCbx sequence designs | 10 | apo binder RMSD, minimum / median | 0.681 / 3.339 A |
| corrected aCbx sequence designs | 10 | hits under saved strict filters | 0 |

One resident Boltz model load served all ten complex predictions and one served
all ten binder-only predictions. The complex stage took 213 seconds and the apo
stage 105 seconds. These are measured workflow timings on the machine in the
header, not general performance claims.

The five raw aCbx binders were compact (radius of gyration 10.686--11.784
Angstrom), had 100% valid adjacent C-alpha geometry and median secondary-
structure assignment of 66.2% alpha helix, 7.7% beta strand and 27.7% coil.
Each placed 11--15 binder residues within 5 Angstrom of 7--9 target residues.
Two were not production-quality at the raw interface: design 0001 contained one
1.873-Angstrom inter-chain heavy-atom contact, while design 0003 contained four
contacts below 2 Angstrom, including a severe 1.202-Angstrom O--NH2 overlap.
Design 0005 gave the most consistent sequence-level foldability signal (binder
pLDDT 0.900/0.915; best apo-vs-bound RMSD 0.681 Angstrom), but still did not
recover the designed toxin-binding pose.

The source-level cysteine atom14 regression, four aCbx integrity tests, four
surface-origin tests, four weight-provenance tests, three resident-predictor
tests, worked-example Foundry preflight, RFdiffusion3 result/ORI UI contract and
both debug and release Swift builds passed.

The cancelled mNeonGreen run reached ten backbone checkpoints. An examined raw
output retained all 1,876 target atoms, including the complete residue-specific
side-chain inventory. The job stopped before sequence design or prediction, so
it provides exporter acceptance only and no enrichment result.

The ten checkpoints nevertheless permit a raw-backbone comparison. They cover
two distinct surface placements (five 55-residue designs at surface-scan-01 and
five 65-residue designs at surface-scan-02). All ten had 100% valid adjacent
C-alpha geometry and no nonlocal C-alpha pairs below 3.5 Angstrom. Their median
radius of gyration was 10.411 Angstrom, versus 20.579 Angstrom across the old
raw-weight 100-backbone campaign (20.653 and 20.414 Angstrom in its matched 55-
and 65-residue groups). Biotite assigned a median 85.8% alpha helix and 14.2%
coil to the new set; the old 55-residue group had median 23.6% helix and 67.3%
coil. No new complex had an inter-chain heavy-atom pair below 2.0 Angstrom;
the old 55-residue group reached 34 such pairs in one design.

The first five new checkpoints exactly repeat the seeds and coordinates from
the completed EMA surface-scan smoke, so ten sequence designs provide an
independent foldability comparison. Boltz binder-to-generated-backbone RMSD was
0.369/0.626/1.615 Angstrom (minimum/median/maximum), versus
2.859/13.529/22.407 Angstrom in the 200 old-weight sequences. Median binder
pLDDT improved from 0.593 to 0.947 and median apo-vs-bound binder RMSD from
15.215 to 0.460 Angstrom. This is strong evidence of better foldable backbone
generation, but not of better binding: median target-aligned bound-pose RMSD
was still 19.741 Angstrom and none passed the saved strict hit filters.

## Decision and rationale

Boltz verification remains template-free. RFD3 already receives and fully fixes
the actual target coordinates; the failures were an invalid target asset and an
export-name bug, not absence of a template. Supplying that same target as a Boltz
template would make pose validation partly circular and could conceal a binder
that does not independently recover its designed interface.

The raw RFD3 structure and independent prediction answer different questions.
The raw structure must preserve the supplied target and atom chemistry. Boltz
then tests whether the designed sequence recovers both binder fold and bound
pose. Strong iPTM/ipSAE without low target-aligned pose RMSD is not promoted to a
hit.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
"$HOME/.iproteinstudio/rfd3/.venv/bin/python" Tests/test_acbx_example_integrity.py
"$HOME/.iproteinstudio/rfd3/.venv/bin/python" Tests/test_rfd3_target_export.py
"$HOME/.iproteinstudio/rfd3/.venv/bin/python" Tests/test_rfd3_surface_origins.py
"$HOME/.iproteinstudio/rfd3/.venv/bin/python" Tests/test_rfd3_worked_examples.py
bash Tests/test_rfd3_results_ui_contract.sh
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swiftpm-cache \
  swift build
/usr/bin/python3 "$HOME/.iproteinstudio/mcp/studioctl.py" \
  job-status job-b402e93db000
/usr/bin/python3 "$HOME/.iproteinstudio/mcp/studioctl.py" \
  job-status job-eb1ed631a657
```

Primary structure source: <https://www.rcsb.org/structure/1CTX>. The downloaded
RCSB file used for the mechanical chain extraction was `/private/tmp/1CTX.pdb`.

## Limits and what was not tested

- The corrected five-backbone aCbx sample is an execution and integrity test,
  not an enrichment benchmark. It produced no strict pose-recovery hit.
- Only one of the calculated surface locations is used when the smoke quota is
  five; this is not whole-target coverage by itself.
- The matched 100-backbone mNeonGreen campaign was cancelled at ten backbones
  before MPNN or prediction. Its final complex, apo and hit distributions do
  not exist; its checkpoints remain resumable.
- The corrected app has not been run on the user's M1 MacBook. The malformed
  bundled asset and atom-name ordering were platform-independent, but M1 runtime
  acceptance remains separate.
- Boltz target-only deviation from 1CTX ranged from 1.978 to 3.603 Angstrom in
  the ten complexes. The recognizable fold does not mean Boltz reproduced the
  experimental target exactly.
- OXT is not represented by the Foundry atom14 canvas, so raw MLX export retains
  540 of the 541 input atoms. This does not alter the backbone or disulfides.

## Next

Run the same aCbx example on the M1 MacBook before calling cross-generation
acceptance complete. Resume the mNeonGreen plan only if a full matched
old-weight/new-weight enrichment comparison is still wanted.
