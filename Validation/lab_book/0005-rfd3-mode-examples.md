---
entry: 0005
title: Validate RFdiffusion3 partial and motif examples
date: 2026-09-02
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
---

## Question

Do Studio's bundled p53–MDM2 partial-diffusion and motif-scaffolding examples
run through the exact app overlay on the Apple GPU, produce one requested
backbone, preserve valid Cα geometry and retain the explicit motif atoms and
residue correspondence needed by downstream analysis?

## Safety and provenance

`Validation/experiments/rfd3_modes_smoke_v1/run.py` creates a disposable
runtime under the requested ignored output directory. It copies Studio-owned
scripts, copies the installed MLX port and then overlays the app's bundled MLX
source. The installed weights, checkpoints and assets are symlinked read-only;
`~/.iproteinstudio` is not edited. The source baseline was commit `e816a3f` plus
the working-tree feature diff recorded in Lab Book 0067.

## Results

Both runs used 200 steps, two recycles, bfloat16, batch size one and seed base
17. The partial output had 0.324 Å binder Cα RMSD from its input and 100% valid
adjacent Cα distances. The motif output mapped A19→A35, A23→A39 and A26→A38;
all nine requested atoms were present, their source-to-design RMSD after one
global fit was 0.000000789 Å, and 100% of adjacent Cα distances were valid. One
motif attempt was rejected and resampled before the requested single retained
output was reached. A fresh SolubleMPNN handoff emitted one sequence in 1.37 s
and retained F/W/L at all three mapped sites.

The full fixture plus MLX stages took 7.697 s for partial diffusion and 33.804 s
for motif scaffolding. These are n=1 correctness measurements, not performance
estimates. Raw outputs and summaries are under:

- `Validation/output/rfd3_partial_exact_overlay_defaults_20260902/`
- `Validation/output/rfd3_motif_exact_overlay_defaults_20260902/`

## Interpretation

The two app-owned mode contracts work on this machine and the motif adapter now
preserves the chemistry it claims to constrain. This does not establish a
motif-scaffolding success rate, target binding or downstream predictor
agreement. The pre-copy insertion-assignment RMSD is deliberately distinct from
fixed-atom drift and predicted motif recovery.

## Not yet tested

No complete multi-backbone campaign, M1 execution, packaged-DMG run, every-engine
verification matrix or experimental binding test was performed. The default
motif-recovery threshold remains editable and awaits empirical calibration.
