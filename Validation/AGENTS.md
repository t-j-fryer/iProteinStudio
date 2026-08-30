# Instructions for AI agents in Validation

This directory is the permanent, reproducible record of iProteinStudio settings
validation. Read this file before creating, running, analysing or interpreting a
campaign here.

## Required practice

1. Put executable experiment code and configuration under `experiments/`.
   Generated jobs belong under ignored `output/`; never edit a completed raw job.
2. Add a dated entry under `lab_book/` and index it in `LAB_BOOK.md`. Record the
   hypothesis, paired controls, hardware, exact commit, engine/checkpoint
   fingerprints, cached-MSA checksum, commands, failures and untested cases.
3. A speed comparison must hold sequences, seeds, sample counts, diffusion
   steps, recycles and MSA inputs constant. A secondary-structure intervention
   is a separate contrast; do not use it as the speed control.
4. Cycle 00 is an initialization structure, not a design. Exclude it from design
   counts and helix-control endpoints unless the analysis explicitly labels it.
5. Resume only atomic, audited units. A structure existing on disk is not enough:
   verify its requested sequence, output cardinality, finite coordinates and
   required confidence files.
6. Fail if MPS is absent or forbidden CPU fallback appears. The one documented
   Boltz `aten::linalg_svd` fallback may be counted and reported, never hidden.
7. Do not call directory replay “persistent inference”. Persistence means one
   loaded model remains alive while later-cycle inputs are produced by MPNN.
8. Raw results do not establish a default. Promote only after paired full-campaign
   validation, output equivalence, restart/cancellation testing and a memory soak.
9. Secondary-structure summaries use Biotite P-SEA on predicted coordinates and
   exclude cycle 00. Do not replace structural assignment with sequence propensity.

## Figure style

Use Arial, black text and axes, inward ticks, no gridlines, transparent SVGs, and
black outlines on bars. Put the exact statistical unit and `n` in the caption.
Never report an unmeasured throughput number.
