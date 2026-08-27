---
entry: 0043
title: Recover the full Protenix Constraint macOS validation record
date: 2026-08-27
author: GPT-5.6
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [protenix, constraints, mps, apple-silicon, provenance, manuscript]
---

## Context

Entries [[0040-protenix-constraint-pocket-engine]] and
[[0042-complete-protenix-constraint-install-contract]] record the Studio port
and product installation contract. They compressed the substantial earlier work
under `/Users/thomasfryer/iProteinHunter-beta/experiments/protenix_constraint_macos`
that made the released model trustworthy enough to expose on a Mac. This audit
reconstructed that work from the ignored 9.2 GB output tree (50,775 files), not
only from its prose summary, so later manuscript writing can separate measured
evidence, compatibility work and product decisions.

The authoritative beta records are Lab Book entries 0062, 0063 and 0066,
`experiments/protenix_constraint_macos/configs/protocol.json`,
`experiments/protenix_constraint_macos/docs/results.md`, and the raw outputs
listed below.

## What was done

### 1. Frozen provenance before inference

- Protenix 2.0.0 source was pinned to Apache-2.0 commit
  `4c355be4553512f72453ecbfb65e69f4c35d1413`.
- The official 368.30-million-parameter
  `protenix_base_constraint_v0.5.0` checkpoint was frozen at 1,475,206,741
  bytes and SHA-256
  `5358025b20b2212853ad75579be04387859557915f398a1d60f6a1a9a0c8c887`.
- Common chemical/model data, package versions, the exact 74-residue target
  MSA (SHA-256 `6968ff0dbb452264ed8c6952a7d2188eed0f113606fe149496b7fdbc38ea5cd8`),
  sequences, constraints, seeds, geometry gates and interpretation limits were
  predeclared. Binder and target lengths were 80 and 74 residues.

### 2. Native-MPS compatibility layer

The experiment-owned patch did more than replace a device string. It:

- required native MPS and rejected `PYTORCH_ENABLE_MPS_FALLBACK=1`;
- forced FP32, Torch triangle multiplication/attention and Torch layer
  normalization, while disabling TF32, CUDA fusion and the diffusion shared-
  variable cache;
- replaced inference-time CUDA cache operations with device-aware release,
  synchronized MPS before timing/memory capture and fixed confidence-path
  device/dtype mismatches;
- prevented CUDA-only layer-normalization imports; and
- strict-loaded the learned constraint checkpoint, failing on any missing or
  unexpected key.

Every full-run log reports native Apple MPS, FP32/Torch kernels, strict load
with no incompatible keys, 368.30M parameters, two chains, 154 tokens, 1,163
atoms and 1,183 MSA rows. CUDA-only packages (DeepSpeed, Triton and
cuequivariance CUDA packages) were deliberately omitted.

### 3. Checkpoint-era ESM diagnosis

The first strict smoke stopped on exactly one missing key:
`input_embedder.linear_esm.weight`. Git history showed that upstream commit
`60b585317510ef8f82af058e1a0d812f4de2303e` enabled ESM for the existing
constraint configuration on 26 January 2026, after the checkpoint's 30 May
2025 release. Current code initializes that absent 2,560-dimensional projection
to exact zeros.

The 5,678,116,398-byte ESM-2 3B model was nevertheless audited on native MPS.
It generated finite 80×2,560 and 74×2,560 FP32 features in 11.3033 s with no
fallback. Because the checkpoint has no learned projection, those features
contribute exactly zero; computing them is cost without model information.
The validated resolution was therefore to disable ESM for this checkpoint and
retain strict loading without modifying the official weights. The final minimal
constraint profile imports ESM lazily and contains neither `fair-esm` nor the
5.7 GB model/sidecar. The preserved historical beta receipt still contains ESM
because it is diagnostic evidence, not a demonstration of the minimal install.

### 4. Staged artifact and functional validation

The predeclared reduced smoke used one recycle and five diffusion steps. It ran
on MPS but produced visibly under-denoised structures: zero of 152 adjacent Cα
distances were within 2.5–4.5 Å, so it correctly failed the geometry gate. A
documented non-confirmatory quality smoke restored the official 200 diffusion
steps at one recycle; all four arms then had complete backbones, finite
coordinates, no severe interchain clash below 1 Å and 100% valid adjacent Cα
geometry.

The full paired profile used 10 recycles, 200 diffusion steps, one sample and
fresh processes for seeds 73001–73003. Four arms preserved identical sequences
and MSAs:

1. no constraint;
2. source-interface pocket at B31/B36/B39;
3. alternative-epitope pocket at B18/B19/B21; and
4. exact A61–B18, A62–B19 and A63–B21 residue contacts, each with an 8 Å
   protein-token (Cα) maximum.

All 12 jobs completed under `caffeinate`, and every output passed schema,
chain/sequence, finite-coordinate, complete-backbone, confidence/PAE, clash and
memory checks. The resumable state stores exact commands and checksums for the
CIF, summary confidence and full-confidence file of every job.

## Results

### Full-profile arm summaries

| Arm (n=3 paired seeds) | Wall time, mean (s) | Forward, mean (s) | Relevant geometry, mean (Å) | pLDDT, mean | iPTM, mean |
|---|---:|---:|---:|---:|---:|
| Unconstrained | 51.906 | 22.013 | alternative-contact violation 20.481 | 82.919 | 0.796 |
| Source pocket | 50.985 | 21.013 | source-pocket distance 5.065 | 84.702 | 0.906 |
| Alternative pocket | 51.008 | 20.797 | alternative-pocket distance 24.744 | 83.855 | 0.836 |
| Explicit alternative contacts | 56.298 | 25.923 | contact violation 0.495 | 82.182 | 0.255 |

Pocket-only priors formally improved the chosen distance in two of three seeds,
but the paired median changes were only −0.039 Å (source) and −0.021 Å
(alternative), with inconsistent seed directions. These are practically
negligible responses, not robust epitope steering.

Exact contacts reduced violation in all three seeds by 19.676–20.374 Å; the
paired median change was −19.908 Å. This strong geometric response carried a
median iPTM change of −0.595 and median pLDDT change of only −0.607. The model
therefore forced a local relationship while strongly disfavoring the resulting
interface. In seed 73001 the three requested Cα distances were 6.222, 9.403 and
7.334 Å: even explicit constraints remained soft, with one 8 Å bound violated.

The explicit-contact arm cost 8.5% more process wall time and 17.8% more model-
forward time than the unconstrained arm. The 12 full jobs consumed 630.59 s
total wall time. Full-profile minimum MPS headroom was 49.17 GiB, maximum RSS
was 5.96 GiB and maximum recorded Metal memory footprint was 31.76 GiB. The
lower 32.43 GiB headroom in the aggregate validation JSON belongs to the first
cold five-step smoke and must not be reported as the full-profile minimum.

An identical-seed repeat was not byte-identical but differed by only
0.00009935 Å all-atom RMSD, which is effectively reproducible for exploratory
MPS inference while remaining honest about nondeterministic hashes.

### Preserved analysis and visualization assets

The raw evidence remains outside Git under:

- `output/protenix_constraint_macos/runtime/install_receipt.json` — historical
  diagnostic environment and exact package receipt;
- `runtime/checkpoint_inspection.json` — 4,109 checkpoint keys, including 17
  learned constraint keys and the enabled pocket/contact/atom/substructure
  embedders;
- `smoke/.../run.strict_esm_failure.log` — the one-key strict-load failure;
- `runtime/cache/esm_embeddings/manifest.json` — native-MPS ESM timing, shapes
  and hashes;
- `full_profile/state.json` and `analysis/run_metrics.csv` — exact commands,
  per-job hashes, timings, memory and structure/confidence paths;
- `analysis/full_arm_summaries.csv`, `full_paired_differences.csv` and
  `validation_summary.json` — the tables behind the values above;
- `analysis/figures/` — Arial, black-axis, no-gridline SVG/PNG figures for
  runtime, paired geometric response and contact/iPTM trade-off; and
- `analysis/chimerax_constraint_comparison/` — three 1,600×1,100 target-aligned
  ChimeraX snapshots/scripts plus a manifest binding all 12 copied CIFs to their
  source SHA-256 values.

The visual outputs make the scientific hierarchy clear: a pocket names target
residues but no binder partners and changed this interface little; explicit
residue pairs robustly reoriented the binder but generated a low-iPTM interface.
They are suitable provenance assets for a future manuscript figure, subject to
final figure selection and captioning rather than being treated as new evidence.

## Decision and rationale

The v0.5 constraint checkpoint is technically validated on this M4 Max. The
Mac result depended on native-MPS device enforcement, portable Torch/FP32
kernels, strict checkpoint-era architecture, removal of a zero-effect ESM path,
fail-loud schema/weight checks, official 200-step denoising and complete output
validation—not on allowing CPU fallback or weakening strict loading.

Studio correctly exposes only coarse protein-pocket proposals and labels the
engine experimental. It does not expose the much stronger residue-contact mode:
that mode produced a dramatic orientation change but also a large within-model
iPTM penalty and needs a separate product/scientific study. The 8 Å Studio
default remains the only tested upstream token-centre setting and must not be
equated with Boltz's 6 Å physical contact control. Every final design still
requires unconstrained independent re-folding and interface inspection.

## Reproduce

Read-only reconstruction from preserved beta outputs:

```bash
cd /Users/thomasfryer/iProteinHunter-beta
PYTHONPATH=experiments/protenix_constraint_macos/src python3 -m unittest discover \
  -s experiments/protenix_constraint_macos/tests -p 'test_*.py'

sed -n '1,260p' output/protenix_constraint_macos/runtime/install_receipt.json
sed -n '1,260p' output/protenix_constraint_macos/runtime/checkpoint_inspection.json
sed -n '1,360p' output/protenix_constraint_macos/analysis/validation_summary.json
column -s, -t < output/protenix_constraint_macos/analysis/full_arm_summaries.csv
column -s, -t < output/protenix_constraint_macos/analysis/full_paired_differences.csv
```

Regenerating the beta analysis without rerunning inference:

```bash
export PYTHONPATH=experiments/protenix_constraint_macos/src
output/protenix_constraint_macos/runtime/venv/bin/python \
  -m protenix_constraint_macos.analysis \
  --protocol experiments/protenix_constraint_macos/configs/protocol.json \
  --output-root output/protenix_constraint_macos
```

## Limits and what was not tested

- One 80+74-residue Bgx complex, three paired full-profile seeds and one M4 Max
  were tested. This is not cross-target generalization or an accuracy benchmark.
- No atom-specific contacts, substructure constraints, constraint-weight sweep,
  distance sweep or ESM-plus-constraint trained checkpoint was tested.
- Confidence is interpreted only within this model family and is not evidence
  of binding. No experimental binding data exist for this validation panel.
- The full beta output tree is ignored and machine-local. The versioned protocol,
  analysis code, tests, patch and documentation preserve its interpretation, but
  long-term manuscript archiving should copy the selected raw CIF/confidence
  files and figures into a checksummed external data deposit.

## Next

For manuscript use, select one ChimeraX overlay plus the paired response and
contact/iPTM trade-off panels, write captions that explicitly distinguish soft
pocket priors from exact contacts, and archive their source CSV/CIF/confidence
files. Scientifically, test pocket-conditioned versus matched unconstrained
cycle-00 proposals across several targets and measure unique interface clusters
that survive sequence design and unconstrained re-prediction before changing the
Experimental label.
