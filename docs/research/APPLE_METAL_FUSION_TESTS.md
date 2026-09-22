# Further Metal optimization candidates

> Historical research snapshot (September 2026). Statements about pending work
> describe that date. For shipped behavior, use the [current runtime guide](../PORTABLE_RUNTIME_IMPLEMENTATION.md)
> and [release guide](../UPDATES_AND_RELEASES.md).

2026-09-19. Follow-up to `APPLE_KERNEL_REVIEW.md`; measured results belong to
Lab Book0170 / Validation0040, on this M4 Max only.

## Precedent and choice

The Anthropic Boltz2 kit fuses normalization, pair operations, attention glue and
sampler work, and also removes repeated host work. Its captured sampler explicitly
steps aside when potentials are enabled. Our Boltz control keeps physical and FK
guidance enabled, so transplanting that sampler would not test our existing path.
[Boltz2 changes](https://github.com/anthropics/uplifting-biomolecular-modeling/blob/main/boltz2/CHANGES.md).

Protenix's kit similarly fuses diffusion/atom attention and transition elementwise
work around its GEMMs, with dtype/shape-specific activation and separate exact and
approximate variants. We test FP32 gating/activation fusions around unchanged
native projections and normalization first. We do not import its CUDA code,
disable checkpoint branches, or substitute its NVIDIA precision assumptions.
[Protenix changes](https://github.com/anthropics/uplifting-biomolecular-modeling/blob/main/protenix_v2/CHANGES.md).

NESSO's own source uses Boltz-derived gated transitions. That provides a shared
operator opportunity, but our previous short-input profile puts most wall time
in preprocessing rather than GPU inference. Session-owned CCD molecule caching
therefore precedes its kernel test. The model is an affinity predictor; a kernel
speed gain must preserve its scalar outputs as well as embeddings.
[NESSO repository](https://github.com/recursionpharma/nesso),
[output contract](https://github.com/recursionpharma/nesso/blob/main/docs/prediction.md).

PyTorch exposes runtime Metal shader compilation directly on MPS tensors; it is
also present in our installed2.7.1 and2.11 runtimes. This avoids requiring a Torch
upgrade or a Torch-to-MLX round trip for this experiment. MLX's existing fast
normalization/attention primitives are useful precedent, not proof that an array
conversion or hand-written replacement will help a Torch engine.
[PyTorch shader API](https://docs.pytorch.org/docs/2.14/generated/torch.mps.compile_shader.html),
[MLX fast primitives](https://ml-explore.github.io/mlx/build/html/python/fast.html).

Apple's Metal tensor/custom-ML guidance motivates combining operations to reduce
intermediate memory traffic and dispatches. Our M4 test does not assume M5 tensor
hardware or establish M1–M5 performance. Replacing a tuned dense GEMM is lower
priority than measured redundant operations around it.
[Apple WWDC26](https://developer.apple.com/videos/play/wwdc2026/330/).

## Prospective experiment

1. Preserve scientific settings, existing engine-specific runtimes and FP32.
2. Measure call counts and representative shapes; synchronized diagnostics are
   excluded from throughput claims.
3. Compare fused SiLU×value, sigmoid×value, and sigmoid×value+bias against a
   NumPy FP64 reference and stock Torch FP32 at relative L2<=1e-5. Retain failures.
4. Include wrapper, broadcasting/layout and dispatch costs in alternating-order
   timings; separate compilation and warmup.
5. Only passing operators reach unchanged full predictions. Use fixed baseline
   SUMO core, confidence/error/geometry checks, and NESSO scalar tolerances.
6. Repeat promising complete-model results in reversed order before considering
   activation. Add larger fixtures, recovery and memory tests for integration.

Larger fused LayerNorm epilogues, online-softmax triangle attention and cached
diffusion conditioning are follow-ups only if profiling and these complete-model
results justify them. A custom kernel is not intrinsically better than the native
MPS implementation.

## Additional findings during implementation

The raw in-process NESSO parser reused the RDKit random stream and changed saved
ligand coordinates, even where final scalar differences passed the0.02 gate.
RDKit documents that randomSeed=-1 leaves the RNG unseeded; its C++ default
generator begins at42, but a persistent process consumes that state across calls.
A diagnostic attempt to reset the Python-exposed RNG did not reproduce the
fresh-process conformer, so it was not used as a guessed fix.
[RDKit embedding contract](https://github.com/rdkit/rdkit/blob/master/Code/GraphMol/DistGeomHelpers/Embedder.h),
[default generator source](https://raw.githubusercontent.com/rdkit/rdkit/master/Code/RDGeneral/utils.cpp).

The replacement caches the exact conformer bytes produced by the ordinary fresh
worker on the first occurrence of each exact SMILES string. Subsequent requests
call upstream parse_schema with its supported conformer input and fresh amino-acid
molecule copies. A bounded LRU holds at most8 conformers. Noncanonical protein
sequences keep the original full-CCD preprocessing path. Every cache hit saves the
actual conformer and its digest for reproducibility. Complete parser-array equality
is audited alongside embeddings, ligand identity and all scored scalars.

The Metal normalization stress test includes nearly constant values around1000;
its simple sum-based mean lost sufficient accuracy to fail the declared FP64
threshold. Ordinary random inputs passing is insufficient, so this kernel stops
before inference. The accepted pointwise kernels retain native LayerNorm and GEMM.

Targeted searches did not identify a maintained Apple-specific drop-in kernel
package for these three installed engines. TT-bio is a relevant example of a
separate hardware port, but its TT-Metal/TT-NN backend is Tenstorrent, not Apple
Metal. Its speed numbers are not used in our Mac comparisons.
[TT-bio hardware scope](https://github.com/moritztng/tt-bio).

## Measured outcome and next priority

The three pointwise fusions passed all45 operator cases across the installed
Boltz, Protenix and NESSO runtimes. They did not produce a general model speedup.
Boltz's original wrapper was19.3% slower; caching shader handles and removing
unnecessary wrapper work brought the reversed-order follow-up to0.3% less time,
effectively parity. NESSO's full calls improved only0.5%. Protenix's initial9.6%
reduction fell to1.9% overall in a second-seed, reversed-order confirmation; its
228-residue synthetic fixture improved5.1%, while its short fixture slowed down.
These are separate process pairs on M4 Max, not statistical estimates of a
universal benefit. No production Metal default is enabled.

NESSO preprocessing was more productive: standard-AA cloning plus exact
first-use conformer reuse reduced the two warmed short requests from18.320s to
2.732s, with exactly equal saved parser arrays, embeddings and scores. A separate
24-output confirmation exercised four ligands and76/96/228-residue inputs; all
outputs remained exact. Its mixed cold/warm requests improved27.2% over the
AA-cache-only control. New ligand requests retain original preprocessing cost.

The next worthwhile kernel experiment would combine more adjacent work per
dispatch, after an uninstrumented GPU trace confirms a substantial share of
runtime. Attention masking/bias/softmax or a stable normalization epilogue have
precedent; another isolated sigmoid kernel does not address the observed
launch overhead. Keep native GEMMs, retain all masks and guidance, and test
irregular shapes and nearly constant activations before any full-model trial.
These larger kernels have not been validated here. The present measurements do
not justify implementing a custom dense GEMM or an M5-only backend on this M4.
