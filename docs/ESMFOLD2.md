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
| Studio tested profile | 3 loops, 50 requested sampling steps | 20 loops, 100 requested sampling steps |
| Pocket restraints / template guidance / Boltz affinity | Unavailable | Unavailable |

Both support protein chains and SMILES ligands. Neither is available as the
Protein Hunter X-token design engine. These experimental MLX predictions are
not claimed to be numerically equivalent to the reference PyTorch model.
The step counts above identify Studio's tested profiles; actual denoising
passes differ because the upstream schedule includes recycling and step reuse.

On our **M4 Max, 40-core GPU, 64 GB**, Fast's model call was about **1.2–1.6×
faster at matched 3-loop/50-step settings**, for one 96-residue monomer and one
194-residue protein complex. Comparing the tested Fast and Full profiles above
was about **4–13×**, but that changes both model size and compute budget. Those
numbers exclude loading, feature preparation and output decoding and are not
whole-campaign estimates or an accuracy comparison. Both comparison inputs were
sequence-only. See [Lab Book 0214](../lab_book/0214-test-esmfold2-fast.md).

## Where the options appear

- **Predict and target preparation:** choose Fast or Full. Fast uses no MSA;
  Full follows the requested MSA policy. Missing requested alignments fail
  rather than silently falling back to sequence-only input.
- **Protein Hunter:** independent checks of completed sequences and final
  small-molecule screening follow-up. Initial X-token hallucination stays with
  the existing design engines. Fast and Full are the same model family, not
  independent evidence of one another.
- **RFdiffusion3:** prediction of MPNN sequences and optional additional checks.
  ESMFold2 is an unrestrained refold, not a continuation of RFD3 conditioning.
- **NISE:** optional final structure checks for any objective. When NESSO or
  PSICHIC is selected as the **optimisation objective**, a separate Structure
  generator selector also offers Fast/Full for the complete-sequence search.

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

The folding trunk uses FP32, ESMC-6B uses BF16, with strict checkpoint loading.
Learned inference runs on MLX/Metal. Feature preparation and decoding use CPU
helpers, including the upstream small CPU SVD; this is not an all-GPU pipeline.
The shipped runtime and asset manifests record package/file hashes and checkpoint
revisions. See [0215](../lab_book/0215-integrate-esmfold2-mlx.md) for release checks,
known limitations and untested cases.

## Protein Hunter refinement

ESMFold2 Fast/Full can refine complete MPNN sequences after an explicit separate
cycle-00 generator. They remain unavailable for X-token hallucination.
See [Protein Hunter stages](PROTEIN_HUNTER_STAGES.md) for guidance scope, MSA
policy and the same portable-runtime setup.
