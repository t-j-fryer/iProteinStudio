# What transfers from the Anthropic acceleration work to this Mac

2026-09-19. Companion to Lab Book0169 and `Validation/experiments/apple_runtime_throughput_v2`. These are M4 Max experiments; no installed engine defaults have changed.

The useful lesson is to optimize the work that actually runs, then validate each change independently and in the complete prediction. Their headline gains are NVIDIA H100 measurements, with different workloads and precision settings from ours; they are not estimates for Apple hardware. Their benchmark distinguishes startup, forward calls and whole tasks, uses strong upstream baselines, and checks practical numerical changes against baseline variability and downstream accuracy. Kernel tests additionally use a float64 reference and alternating measurement order. [Technical report, Methods, SI introduction and S9](https://www-cdn.anthropic.com/c93593cb8990d6c0e2644c22b1e4e74228eeb013.pdf).

The report's NVIDIA MPS means Multi-Process Service, not Apple's Metal Performance Shaders. Its CUDA/Triton kernels require a new implementation for Metal; the profiling, caching and validation methods transfer more directly.

Our immediate application is to retain unchanged scientific settings, use separate stage profiles, compare the installed runtime with2.14, and isolate implementation changes. The initial short monomers are screening fixtures. They do not establish speed or interface-quality retention for larger complexes. SUMO's flexible tail is separated by excluding fixture residues1–20, then selecting the baseline-defined pLDDT≥80 core (minimum20 residues). This conservative comparison mask is fixed for the candidate too. Random-draw replay distinguishes arithmetic drift from a framework RNG change; it is not a throughput measurement.

| Published technique | Apple interpretation and current action |
|---|---|
| Compute diffusion invariants once | Protenix already exposes an upstream cache, now under test. For any additional cache, document precisely what depends on sequence, coordinates, step, conditioning and sample. Rebuild at the correct boundary. |
| Fuse attention, normalization, projections and gating | First compare existing framework primitives. The OpenFold prototype uses native Torch SDPA with the model's existing query scaling preserved. The RFD3 experiment compares eager MLX, compiled MLX, MLX SDPA and direct-load Metal attention. |
| Capture repeated work to reduce launch overhead | CUDA graphs are not an Apple API. Measure compiled MLX blocks or supported Torch compilation on the actual shape, including compilation cost and graph breaks, before attempting a whole-model rewrite. |
| Avoid redundant startup and host work | Measure loading, preprocessing and writing separately. NESSO's dictionary cache is being tested; AntiFold's short calls get an additional both-shapes-warmed check. |
| Select kernels by actual device and workload | Record dtype, shape, strides, mask form, runtime and activation counts. A fast operator on one shape is not a universal backend. Keep the existing implementation available and make unsupported cases explicit. |

The Protenix kit combines fused pair operations with cached sampler work and avoids some checkpoint-overwritten initialization and provably inactive checkpoint branches. Its near-zero-weight branch optimization is checkpoint-specific; we must not copy its module list to our checkpoints without proving equivalence. The initial cache experiment uses our installed upstream implementation rather than transplanting their CUDA stack. [Protenix changes](https://github.com/anthropics/uplifting-biomolecular-modeling/blob/main/protenix_v2/CHANGES.md).

The OpenFold kit also addresses startup and output overhead: skipped overwritten initialization, mapped checkpoint loading, invariant pair/atom conditioning and an output writer. These are candidates after our reload-inclusive profile identifies their importance. They need independent request-reset, RNG and output tests. Its kernels and CUDA capture cannot simply be enabled on MPS. [OpenFold changes](https://github.com/anthropics/uplifting-biomolecular-modeling/blob/main/openfold3/CHANGES.md).

The RFD3 kit caches invariant projections, fuses feed-forward work and changes attention execution. Our native MLX port already differs from their Torch baseline, so some work may already be fused or absent. In particular, coordinate-dependent neighbor indices must still update during diffusion. [RFD3 changes](https://github.com/anthropics/uplifting-biomolecular-modeling/blob/main/rfdiffusion3/CHANGES.md).

## Custom Metal kernels

They are a credible option. MLX exposes `mx.fast.metal_kernel`; PyTorch2.14 exposes `torch.mps.compile_shader`. These let an implementation remain within its engine's existing array framework. Moving Torch tensors into MLX solely to call a kernel needs an explicit transfer, lifetime and synchronization analysis; unified memory alone does not prove that conversion is free. [MLX API](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.fast.metal_kernel.html), [PyTorch API](https://docs.pytorch.org/docs/2.14/generated/torch.mps.compile_shader.html).

The first custom prototype fuses sparse neighbor lookup and attention, avoiding materialized gathered K/V buffers. It keeps the same neighbors, bias and output gate. The numerical experiment uses existing FP32/BF16 operands, FP32 attention accumulation, a NumPy float64 oracle, irregular/repeated neighbors and an infinite mask. It is compared with both compiled high-level MLX and native SDPA, not just an unfused baseline. Compilation and synchronized steady-call time are separate. Only a passing, worthwhile operator should progress to complete unchanged-step trajectories.

Our inference: this is a more informative first Metal experiment than replacing optimized matrix multiplication. Larger triangle kernels may be worthwhile later, after representative complex-size profiles show sufficient time there. The immediate priority is measuring actual end-to-end benefit, including layout changes and memory use, rather than reproducing NVIDIA kernel names or performance claims.

The published repository is an unmaintained reference release with pinned upstream versions. Any port therefore needs its own provenance, tests and supported-shape contract. Its activation/accounting approach is useful: record which optimization actually ran. [Repository](https://github.com/anthropics/uplifting-biomolecular-modeling).

PyTorch2.14 specifically moves more indexing and reduction work from MPSGraph to native Metal and expands GPU linear algebra. This gives a plausible mechanism for improvements in these launch-heavy predictors; it does not establish which change caused any measured gain. Our NESSO regression is a reason to keep runtime selection per engine. [Official2.14 release notes](https://pytorch.org/blog/pytorch-2-14-release-blog/).

For eventual distribution, Apple supports compiling Metal source strings through the runtime framework as well as loading prebuilt libraries. Our inference is that custom kernels need not automatically create a user-facing Xcode installation requirement; the selected MLX/Torch path still needs a clean-Mac installation test, separate from these performance tests. First-call compilation costs and shader-cache compatibility must be recorded. [Apple Metal runtime compilation API](https://developer.apple.com/documentation/metal/mtldevice/makelibrary(source:options:completionhandler:)).

## What the tests taught us

The direct-load Metal kernel passed eight independent FP64 shape/dtype cases and was faster than compiled MLX as an isolated operator. It also shortened complete RFD3 calls against an earlier reference, but one trajectory exceeded the prespecified coordinate tolerance. A second implementation matched its explicitly rounded arithmetic oracle yet differed too much from MLX itself, so it stopped before prediction. Neither kernel is qualified for production.

Native MLX SDPA passed the trajectory checks, but its apparent26% gain against an earlier control disappeared in a fresh reversed-order pair: it was5.5% slower. This directly supports the report's emphasis on a strong, contemporaneous baseline. We retain the existing RFD3 implementation; an isolated kernel speedup or an older slow reference is insufficient.

The clearer current opportunities are computational waste and CPU setup: smaller IntelliFold padding tensors and cached NESSO CCD parsing. Thread tests also changed direction between Torch versions; four threads beat one on the tested2.14 Flash path, while one beat four on2.6. Tuning must be attached to the measured runtime and workload. Exact measurements, failed attempts, core masks and repeat caveats are in [the benchmark report](../Validation/output/apple_runtime_throughput_v2/REPORT.md) and Lab Book0169.
