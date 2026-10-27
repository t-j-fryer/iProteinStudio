# ESMFold2 on Apple silicon (experimental)

Install **ESMFold2 Fast MLX** or **ESMFold2 Full MLX** in Engines. Studio downloads
a verified portable runtime and revision-pinned Biohub weights. No terminal,
Python, Git, Xcode or Homebrew installation is required. This runtime requires
Apple silicon and macOS 26.2 or newer. The two variants share the approximately
25.4 GB ESMC-6B download; each adds its own folding checkpoint. Model assets are
not included in the app or runtime archive.

## Choosing a model

| | Fast | Full |
| --- | --- | --- |
| Protein input | Complete sequences | Complete sequences, optionally with an MSA |
| MSA encoder | Absent | Present |
| Folding trunk | 24 layers | 48 layers |
| Studio tested profile | 3 loops, 50 requested sampling steps | 3 loops, 50 requested sampling steps |
| Pocket restraints / template guidance / Boltz affinity | Unavailable | Unavailable |

Both support protein chains and SMILES ligands. Full also supports Protein
Hunter CDR-only X-token initialization within a fixed nanobody framework.
Fast and whole-chain X-token initialization remain unsupported. These experimental MLX predictions are
not claimed to be numerically equivalent to the reference PyTorch model.
The step counts above identify Studio's tested profiles; actual denoising
passes differ because the upstream schedule includes recycling and step reuse.

On our **M4 Max, 40-core GPU, 64 GB**, Fast's model call was about **1.2–1.6×
faster at matched 3-loop/50-step settings**, for one 96-residue monomer and one
194-residue protein complex. The historical comparison against Full at 20 loops/100 steps
was about **4–13×**, but that used different compute budgets and no longer
represents the app defaults. Those
numbers exclude loading, feature preparation and output decoding and are not
whole-campaign estimates or an accuracy comparison. Both comparison inputs were
sequence-only. See [Lab Book 0214](../lab_book/0214-test-esmfold2-fast.md).

## Where the options appear

- **Predict and target preparation:** choose Fast, Full or 600M. Fast and 600M use no MSA;
  Full follows the requested MSA policy. Missing requested alignments fail
  rather than silently falling back to sequence-only input.
- **Protein Hunter:** independent checks of completed sequences and final
  small-molecule screening follow-up. Full can initialize selected nanobody CDRs;
  the framework and target must contain complete standard sequences, and scaffold
  alignment CDR columns are masked. Fast, Full and 600M are the same model family, not
  independent evidence of one another.
- **RFdiffusion3:** prediction of MPNN sequences and optional additional checks.
  ESMFold2 is an unrestrained refold, not a continuation of RFD3 conditioning.
- **NISE:** optional final structure checks for any objective. When NESSO or
  PSICHIC is selected as the **optimisation objective**, a separate Structure
  generator selector also offers Fast/Full/600M for the complete-sequence search.

## NISE with ESMFold2 structures

1. Generate initial backbones with the selected generator. Protein Hunter
   X-token initialization uses Boltz; RFdiffusion3 initialization is unchanged.
2. Sample complete sequences with LASErMPNN. The existing NESSO/PSICHIC stage
   shortlist controls determine which sequences receive a fold.
3. ESMFold2 predicts the complete protein–ligand structure **without pocket
   guidance, templates, affinity or MSAs**. Full is intentionally sequence-only
   in this NISE route. Both models' original ligand coordinates are retained.
4. Apply the existing Bind, Expose/linker-exit and stage-specific RMSD checks.
   Ligand names are translated through an audited identical-SMILES atom map,
   never by spatial proximity or assumed matching indices.
5. The selected NESSO/PSICHIC objective controls winners, seed selection, beam
   advancement, best-so-far and patience. ESMFold2 confidence is reported
   separately and is not added to that objective. Early-gate defaults remain
   0.4 for NESSO and 0.2 for PSICHIC.

Unrestrained folding can change ligand placement and rejection rates. This is
an explicit experimental alternative, not a transparent substitute for guided
Boltz folding. The original geometry checks remain active. An optional final
refold does not change the campaign's optimisation score or acceptance decision.

NISE reuses one ESMFold2 session for each stage and, with across-cycle reuse,
keeps that session alive while later sequences are produced. It does not create
a two-worker ESMC-6B pool. Across-cycle retention also keeps the sequence scorer
loaded and uses more memory. Predictions commit and appear individually;
resume verifies input identities and saved artifact checksums before reuse.

## Attribution and reproducibility

The MLX model implementation is **Fausto Milletari and contributors' unofficial
port**, pinned at `c26b9af872158d822a8c95589708eedd3b9c0831` from
[faustomilletari/mlx-lm](https://github.com/faustomilletari/mlx-lm), proposed in
[MLX-LM PR 1484](https://github.com/ml-explore/mlx-lm/pull/1484).
Original ESMFold2 and ESMC models and CPU input/output helpers are by
[Biohub](https://github.com/Biohub/esm); MLX and MLX-LM are by Apple and contributors.
Studio supplies installation, orchestration, audited I/O and UI integration.
Upstream model code and licences are retained in the portable runtime.

Folding weights and residuals use FP32; the pinned MLX folding trunk internally
computes in BF16. ESMC-6B uses BF16, with strict checkpoint loading.
Learned inference runs on MLX/Metal. Feature preparation and decoding use CPU
helpers, including the upstream small CPU SVD; this is not an all-GPU pipeline.
The shipped runtime and asset manifests record package/file hashes and checkpoint
revisions. See [0215](../lab_book/0215-integrate-esmfold2-mlx.md) for release checks,
known limitations and untested cases.

## Protein Hunter refinement

ESMFold2 Fast/Full/600M can refine complete MPNN sequences after an explicit separate
cycle-00 generator. Full can also perform the fixed-framework CDR initialization
described above. Whole-chain monomer and minibinder X-token starts are unsupported.
See [Protein Hunter stages](PROTEIN_HUNTER_STAGES.md) for guidance scope, MSA
policy and the same portable-runtime setup.

## Memory controls and ESMFold2Fast-600M

Full retains the large ESMC-6B encoder. Chunking cannot remove that weight-memory
floor. Existing Full calibration measured 20.25 GiB of process-tree accounted
footprint at 96 residues on an M4 Max with 64 GB RAM; this is neither exact
physical RAM nor a measurement on a 16 GB Mac. See Lab Book 0581 for the newer
bounded cache/chunk controls and their explicit limitations.

CLI/MCP `prediction_settings` for Full, Fast and the 600 beta accept
`chunk_size` (0 means disabled) and `cache_limit_mib` (0–4096 MiB). The existing MLX hook
chunks pair/MSA **transition layers**, not every attention operation. It trades
activation memory against overhead and cannot guarantee a smaller total peak.
The cache cap limits reusable MLX allocations, not live tensors or total process
memory. These choices are retained in the immutable plan, prediction profile
and completion identity. Full/Fast defaults remain 0 and 4096 MiB.

**ESMFold2Fast-600M** (`esmfold2-600-mlx`) is an opt-in experimental predictor
in the app, CLI and MCP. It uses the pinned Synthyra 24-block checkpoint,
ESM++ 600M encoder and experimental confidence head. It is a distinct model,
not Full or release Fast with smaller settings.

Choose it for complete-sequence monomers, protein complexes, protein–SMILES
complexes, sequence target preparation, RFD3 checks, RFD4 protein/nanobody
sequence search, or Protein Hunter refinement after a separate initialization.
Custom workflows retain this choice when saved. NISE can use it for completed
sequence folding with a NESSO/PSICHIC objective or final structural checking.
Boltz remains necessary for Boltz affinity objectives, including RFD4 ligand search.
600M has no MSA encoder, X-token initialization, template/pocket guidance or
binding-affinity head. Fast, Full and 600M are the same model family and must
not be represented as independent-family validation.

Install in **Engines → ESMFold2Fast-600M**, or through the managed CLI:

```sh
bash "$NANOHUNTER_ROOT/setup_pipeline.sh" --with-esmfold2-600
```

The installer provides the existing self-contained MLX runtime plus pinned
600M model/encoder and shared CCD data. ESMC-6B and Full/Fast head weights are
not dependencies. The two learned checkpoints total about 3.02 GB, excluding
shared CCD data and runtime. macOS 26.2+ and Apple silicon are required.
Select `esmfold2-600-mlx` in typed prediction, target, iterative, RFD3, RFD4 or
NISE plans where supported, then start the returned immutable plan with its digest.
Automatic alignment is skipped for sequence-only engines; explicit imported
alignments are rejected when no selected engine can use them. Mixed Boltz/Full
jobs retain the requested MSA policy for those engines.

Profiles expose transition `chunk_size` and `cache_limit_mib`; defaults are
0 and 512 MiB for 600M. **Use low-memory settings** selects 32 and 512 MiB.
These are allocator/transition controls, not a total RAM cap. Memory admission
remains uncalibrated and requires an explicit recorded override. Do not infer
safe input lengths on a 16 GB Mac from the smaller acceptance cases.

Outputs preserve the model/encoder revisions, exact profile, seed, sample,
model-call time and MLX memory counters. Standard confidence files expose pTM,
ipTM when available, complex/per-chain pLDDT, ligand pLDDT on the 0–100 scale,
PAE arrays and protein-interface ipSAE. Monomers rank by pTM; complexes by ipTM.
The experimental confidence head is not calibrated for binding efficacy.
See [integration qualification](../lab_book/0586-integrate-esmfold2-600-release.md)
for tests and remaining limits.

Synthyra's [FastPLMs documentation](https://github.com/Synthyra/FastPLMs/blob/main/docs/esmfold2.md)
describes CUDA optimizations. Those kernels and GPU timings do not transfer to
Metal automatically. This beta reuses the already installed MLX primitives;
its checkpoint coverage and isolated confidence-head arithmetic are checked,
but whole-model PyTorch/CUDA parity and predictive accuracy remain unqualified.

The user-requested four-target Figure 2a resident benchmark is recorded separately
in [Lab Book 0582](../lab_book/0582-benchmark-esmfold2-600-figure2a.md). The citrate synthase dimer supplies a large-complex memory example; it does not
establish broad complex accuracy.

The completed benchmark recorded40 measured predictions plus8 warmups on M4 Max/64 GB.
For the 370-residue MBP monomer, whole-session accounted footprint fell from 11.13
to 7.31 GiB with the combined low-memory setting, while mean warmed request time
increased from 9.18 to 13.47 s. For the 916-residue dimer, footprint fell from 28.31 to 18.02 GiB,
with mean request time 76.01 to 84.51 s. These are five seeds per resident session,
not five cold starts, and cannot certify a 16 GB Mac. The dimer still exceeded 16 GiB
in both footprint and MLX allocator measurements. See Lab Book 0582 for all four targets,
separate counters, output audits, host observations and accuracy limitations.
