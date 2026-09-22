# Apple Silicon throughput research and validation plan

> Historical research snapshot (September 2026). Statements about pending work
> describe that date. For shipped behavior, use the [current runtime guide](../PORTABLE_RUNTIME_IMPLEMENTATION.md)
> and [release guide](../UPDATES_AND_RELEASES.md).

Research date: **19 September 2026**. The research snapshot below is followed by
the initial isolated Boltz measurements in [Lab Book0168](../../lab_book/0168-test-isolated-apple-runtimes.md).
**No production performance profile has been promoted.**

The objective is more completed, numerically valid work per hour across M1–M5
and future Apple Silicon. Preserve each model, checkpoint and scientific
protocol. Prefer upstream implementations, then make narrowly scoped changes
where traces show a bottleneck. Publish successful execution profiles through
the [modular distribution architecture](DISTRIBUTION_AND_ACCELERATION_PLAN.md).

**User constraint:** MPNN CPU speed is satisfactory. Retain CPU execution for
ProteinMPNN, SolubleMPNN, LigandMPNN, AbMPNN and LASErMPNN. Their GPU migration is
not an active optimization project. Include their elapsed time in pipeline
measurements; revisit only if it becomes a demonstrated throughput bottleneck.

## Execution update: agreed constraints

The user authorized isolated testing after this research review. Scientific
settings stay fixed: changing model size, diffusion steps, guidance, recycles
or MSA content is outside this optimization work. Numerical acceptance should
reflect protein-design decisions, not require bitwise identity. Avoid assuming
that agreement with the current baseline establishes accuracy.

The declared first Boltz screen and execution record are in
[experiment manifest](../../Validation/experiments/apple_runtime_throughput_v1/manifest.json)
and [Lab Book0168](../../lab_book/0168-test-isolated-apple-runtimes.md).
Its provisional margins are 0.5 A aligned C-alpha RMSD, 1.5 A displacement p95,
0.02 normalized confidence change, 0.5 A PAE MAE and 2 A PAE-error p95, alongside
hard identity/finite-output/cardinality/no-new-backbone-break gates. These are
screening decisions, not experimentally established biological error tolerances.
Do not apply a monomer pass to interface scores or ligand affinity.

For the next protein-interface confirmation suite, prospectively test ipSAE(min)
and iPTM absolute changes (initial screening margin0.02), binder-to-target aligned
interface displacement, geometry/clashes and top-50 selection stability. Treat
near-tied score swaps separately from losing clearly separated candidates.
A target for investigation is at least45/50 shared selections where the pool
has at least100 independent candidates; report rank and threshold flips and
baseline-repeat overlap alongside it. These are proposed criteria requiring
calibration before that confirmation dataset is run. Experimental hit-rate
non-inferiority cannot be established by computational agreement alone.

CPU tuning must budget processes times threads, cap resource use by workload
and memory, and measure useful completed work. Test4/1/8/12 intra-op threads
on the development machine, interop1, then independently test parallelizable
preparation/scoring processes. Preserve per-item seeds and ordered identities.
Retain CPU MPNN; do not equate high CPU utilization with faster whole pipelines.
No capability profile should be selected only from the chip name.

## 1. Evidence and scope

Reviewed the active Studio repository, managed engine sources, top-level venv
package metadata, runtime adapters and prior correctness/scheduler records.
`setup_pipeline.sh --detect` completed with all currently selectable components
reported installed. That is installation detection, not fresh scientific
acceptance. Called four `workflow_guide` routes through the read-profile MCP
bridge; its audit location was redirected into the repository because the
default runtime audit location was outside writable roots. No job was started
during that research phase; subsequent benchmark jobs are documented separately.

The reproducible inventory (local artifact: `lab_book/artifacts/0166-apple-throughput-research/inventory.json`)
records 17 source-file hashes and bounded evidence excerpts, plus 39 installed
package metadata records. It does not import models or read weights. Companion
inventory.py (local artifact: `lab_book/artifacts/0166-apple-throughput-research/inventory.py`)
can repeat the audit. Source observations establish candidate work, not which
operator dominates runtime: actual dispatch and timing require profiling.

The inventory covers every active scientific engine family/checkpoint choice
and the support stages on their execution paths. It is not a review of every
transitive dependency or an assertion that every upstream optional mode ships.
AlphaFold 3 and IntelliFold JAX are retired compatibility identifiers; do not
reactivate them as a speed experiment. Full/Mini/Flash checkpoints remain
different models, not interchangeable acceleration profiles.

| Tool or variant | Current computational route | First investigation; accuracy obligations |
|---|---|---|
| Boltz-2 structure | Torch 2.13.0, native MPS; resident worker; conservative FP32 and allocator-reset mitigation | Torch 2.14 at unchanged settings, then trace trunk, diffusion, guidance, SVD and confidence separately |
| Boltz-2 physical/FK guidance and contact guidance | Extra coordinate/potential work and potentially multiple internal particles; distinct from requested output count | Preserve every guidance setting/particle count; optimize operations only; record each mode separately |
| Boltz-2 affinity | Optional separate checkpoint, loaded as needed by the resident adapter | Reuse verified structure/features where mathematically valid; measure head cost and model-switch memory; keep head outputs unchanged |
| IntelliFold v2 Flash / full v2 | Torch 2.6.0 MPS; bucketed token tensors; pair/MSA/triangle operations and diffusion; resident support | Upgrade each checkpoint independently, reduce padding, tune chunking, investigate attention fusion; retain atom-index compatibility patches initially |
| Protenix v2 / Mini | Torch 2.7.1 MPS; patch selects Torch triangle implementations | Upgrade, then attention/triangle contractions and preprocessing; full v2 currently uses cycle waves, Mini residency |
| Protenix Constraint v0.5 | Separate Torch 2.7.1 environment, strict ESM-free profile, pocket-conditioned prediction | Same kernel work, separately test constraint routing and outputs; never silently add an ESM path |
| OpenFold-3-MLX | Torch 2.6.0 + MLX 0.32.0; Studio requests MLX attention/triangle/activation switches | Establish actual dispatch; compare current route with new native MPS and modern MLX interop; separately investigate supported residency |
| RFdiffusion3 | Native MLX port, declared MLX 0.32.0; BF16 default generation profile, explicit FP32/int8 alternatives; sparse atom and token attention | MLX 0.32.2 at identical precision first, then fused attention, gather/reduction, compiled blocks, diffusion-width/cache tuning |
| NESSO-1 | Declared Torch 2.11.0, resident FP32 MPS, optional scientific screen | Upgrade without changing screening policy; profile embedding, featurization, refinement and scoring separately |
| ESM-2 650M within NESSO | Resident masked-language-model wrapper; requests all hidden states, consumes last; writes/reloads embedding files | Test last-layer-only/base-model route for identical embeddings, length batching and exact-sequence caches |
| ProteinMPNN / SolubleMPNN / LigandMPNN / AbMPNN | Shared Torch 2.2.1 CPU runner; distinct weights/modes | Retain current execution. Regression checks only when packaging/dependency changes touch them |
| LASErMPNN | Torch 2.2.1, native graph extensions; Studio defaults CPU | Retain CPU. Protect extension ABI and sampling/ligand-feature parity during packaging |
| AntiFold | Torch 2.2.0; upstream selects MPS when available; cycle-wave batching/logit reuse already exists | Later compatibility upgrade and batch/memory checks; no blanket replacement of inverse-folding algorithms |
| Target MSA / template alignment | Remote ColabFold service and local cached alignments/conversion; pinned Kalign for applicable templates | Cache verified identical requests, avoid duplicate conversion; network latency measured separately from local compute |
| Ligand preparation | RDKit conformers/force fields/chemical features, CCD parsing | Cache invariant chemistry; bounded CPU threading and prefetch; preserve atom identity, stereochemistry, seeds and conformer protocol |
| Structure parsing and scoring | Gemmi, Biotite, NumPy/SciPy, ProDy, ipSAE, RMSD, geometry and SASA helpers | Parse once where possible, reuse chain maps, vectorize measured hot loops; preserve score definitions and coordinate checks |
| Orchestration and result presentation | Shell/Python process boundaries, immutable receipts, JSON/CIF writing, Swift UI/viewers | Trace launch/serialization waits; bounded CPU overlap, incremental result ingestion; preserve atomic resume and exact output counts |

Declared locks for NESSO/RFD3 come from the prior distribution inventory; the
new installed-metadata scan deliberately excludes component-local environments.
No engine acceptance is inferred from package metadata alone.

## 2. What recent Apple software enables

**Runtime upgrades are the first controlled contrast.** Stable PyTorch 2.14.0
was released September 2. It adds native MPS SVD/QR/Cholesky and other linear
algebra, more direct Metal indexing/reduction kernels and allocator/copy changes.
Its MPP attention path requires macOS 26.2+, FP16/BF16, supported head dimensions
(64/96/128/256) and query length greater than eight. It can benefit older Apple
Silicon too. These are upstream capabilities, not measured Studio gains.
[PyTorch 2.14 release](https://pytorch.org/blog/pytorch-2-14-release-blog/).

PyTorch 2.13 introduced MPS FlexAttention, making custom attention masks a
candidate for fused execution. Dense attention should also be compared with
ordinary scaled-dot-product attention (SDPA). Neither API justifies changing a
model's trained attention pattern. [PyTorch 2.13 release](https://pytorch.org/blog/pytorch-2-13-release-blog/).

The latest MLX release observed is 0.32.2, with additional attention paths and
correctness fixes. Use a matching tested MLX/Metal package set, not independently
floating versions. [MLX releases](https://github.com/ml-explore/mlx/releases).

**M5 has matrix accelerators inside the GPU.** These are separate from the Apple
Neural Engine. Apple describes MLX acceleration on macOS 26.2+; LLM benchmarks
do not predict protein-model gains. Dense projections/attention are plausible
beneficiaries; irregular gather, small reductions, CPU preparation and output
writing need their own treatment. [Apple MLX/M5 research](https://machinelearning.apple.com/research/exploring-llms-mlx-m5).

Apple's TensorOps/Metal Performance Primitives provide portable tensor kernels
with hardware-specific acceleration. The WWDC26 material also covers newer
quantized formats and OS-specific features; availability must be checked against
the installed stable OS and SDK. Custom kernels should use this supported route
when it fits the measured operation. [Apple TensorOps session](https://developer.apple.com/videos/play/wwdc2026/330/).

**FP32 storage does not guarantee FP32 arithmetic.** MLX's tagged 0.32.2
documentation says float32 matrix-family operations may use reduced precision
on suitable hardware, controlled by `MLX_ENABLE_TF32`. Establish an explicit
strict reference process with it disabled, and test the default separately.
Record effective policy before framework initialization. Do not change an
existing campaign's arithmetic silently. [Versioned MLX precision documentation](https://github.com/ml-explore/mlx/blob/v0.32.2/docs/src/usage/precision.rst).

**Compilation is worth testing at block boundaries.** PyTorch 2.14's Metal
code generator still labels itself incomplete; successful compilation of an
elementwise block is not proof that a complete predictor is accelerated.
Start with deterministic, repeated blocks, record graph breaks/recompiles, and
time the first invocation as well as warm execution.
[Tagged PyTorch MPS compiler](https://github.com/pytorch/pytorch/blob/v2.14.0/torch/_inductor/codegen/mps.py).

MLX compilation can fuse operations; shape changes may trigger recompilation.
Shape-independent compilation requires care with shape-dependent Python logic
and RNG state. Try a small supported shape set before a whole diffusion loop.
[MLX compilation](https://ml-explore.github.io/mlx/build/html/usage/compile.html).

NVIDIA-specific Triton/CUDA/CUTLASS kernels and CUDA Graphs are not drop-in Mac
optimizations. Their general lessons—reduce memory traffic, fuse repeated work,
avoid unnecessary synchronization—remain useful. A whole-engine MLX rewrite,
Core ML/ANE conversion or quantization would require a larger scientific port
and maintenance effort. Keep these as later research, justified by profiles.

## 3. Concrete opportunities, in priority order

### A. Build a trustworthy baseline and upgrade runtimes

For each engine, preserve a complete baseline environment and construct an
isolated candidate with the current stable Torch or MLX. Keep weights, engine
commit, patches, inputs, recycles, diffusion schedule, samples, seeds, guidance,
MSAs and precision fixed. Keep other dependencies fixed where compatible; if a
new Python, NumPy or extension ABI is necessary, record that as a runtime-bundle
contrast rather than attributing everything to Torch.

First wave: Boltz 2.13→2.14, IntelliFold Flash/full 2.6→2.14, Protenix
2.7.1→2.14, and RFD3 MLX 0.32.0→0.32.2. A failed direct upgrade becomes a
compatibility task; use intermediate versions only to locate regressions.
OpenFold's mixed-framework upgrade and NESSO follow with dedicated tests.
AntiFold is lower priority; leave satisfactory CPU MPNN environments alone.

Boltz's allocator mitigation must remain in the first upgrade arm. The upstream
silent-matmul issue remains open and describes an allocator change masking its
reproducer, not a demonstrated root fix. Later, compare mitigation retained
versus removed only after allocator stress tests, especially on M1. Retain
IntelliFold's index-selection workarounds until their replacements independently
pass. [PyTorch issue 193487](https://github.com/pytorch/pytorch/issues/193487),
[local M1 correction record](../../lab_book/0061-finish-m1-predictor-correctness.md).

Native SVD deserves a separate Boltz microbenchmark using actual small alignment
matrix shapes. Test singular/near-degenerate cases, rotation handedness and
coordinate alignment. A new supported GPU operation might still be slower than
the small, documented CPU fallback. Count and time any retained exception.

### B. Stop avoidable repeated work

Keep existing predictor residency and test changes against that baseline.
Earlier work already selected different schedules for full Protenix and Mini;
do not assume a permanent worker always wins. New Torch/OS versions may change
that result. Repeat on actual campaigns as well as fixed-input replay.
[Existing resident architecture and measured evidence](../RESIDENT_INFERENCE.md).

For NESSO, source shows `AutoModelForMaskedLM(..., output_hidden_states=True)`
while only the final embedding is consumed. Investigate avoiding the unused
language-model head and retention of every layer output. Require identical
tokenization, BOS/EOS handling, weights and embedding values before accepting
this as equivalent. Cache an embedding only for an identical sequence,
checkpoint/tokenizer revision, dtype and numerical policy. Cache ligand
features only if atom ordering, conformer seed, chemistry and parameters match.
Changing a sequence invalidates its embedding cache. Keep a reconstructible
artifact even if the worker handoff becomes in-memory.

For all predictors, cache only invariant preprocessing: parsed CCD records,
validated target/template conversions and exact alignment features. Learned
target/pair representations often depend on the complete complex and recycling;
they cannot generally be reused when another chain changes. Diffusion steps
also change coordinates/conditioning; LLM-style KV caching is not automatically
valid. Trace and remove redundant parsing or serialization, not computations
that encode changed inputs.

CPU preparation for the next independent item may overlap current GPU work
under the same owner. Bound workers and memory, preserve output/RNG ordering,
and keep one GPU owner initially. Resident models compete for unified memory;
holding structure, affinity, ESM and an orthogonal predictor simultaneously
may be worse than deliberate transitions on a small Mac.

### C. Reduce attention and triangle-operation memory traffic

The common predictor workload contains projections, pair representations,
triangle multiplication/attention, atom-token conversions and repeated diffusion
blocks. Pair state scales quadratically with token count; some triangle
contractions have cubic token dependence. Profile actual tensor shapes and
strides rather than importing LLM sequence-length rules wholesale.

Compare existing attention with SDPA/MLX fast attention where additive pair
bias, mask semantics, scaling, gating and output dtype can be preserved. Sparse
atom attention is a separate candidate for FlexAttention or a fused gather–
attention kernel; preserve its exact neighborhood. Test all-masked rows,
broadcast biases, multiple samples, odd lengths and noncontiguous views. Do not
make dense trained attention sparse to obtain a speed claim.

For triangle multiplication and outer-product mean, consider tiled contraction,
avoiding materialized expansions, layout reuse, and fusion of normalization,
projection, gate and residual operations. Prefer validated upstream kernels.
Write custom Metal only after a trace identifies a costly block and the simple
framework alternatives fail. Keep an eager reference and a generic Metal path.
[MLX custom-kernel API](https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html).

RFD3's inspected port explicitly forms attention scores and performs softmax
and value aggregation; sparse attention gathers K/V and pair bias before
reducing. These are concrete fusion candidates. Preserve FP32 softmax and other
stability-sensitive arithmetic present in the current path, even when linear
weights use BF16. Neighbor membership/tie handling and per-step coordinate
updates must remain equivalent; stale-neighbor reuse is a different algorithm.

### D. Resolve OpenFold's backend boundary before rewriting it

Studio emits `use_mlx_attention`, `use_mlx_triangle_kernels` and
`use_mlx_activation_functions`. The managed `attention_mlx.py` adapter contains
Torch→CPU→NumPy→MLX conversion and a return through NumPy/Torch. Static inspection
did not establish that every configured switch actually dispatches to those
functions. Instrument call counts, actual module paths and device traces first;
the flags and package name alone are insufficient evidence.

Compare three arms: verified existing dispatch; equivalent native Torch 2.14
MPS blocks; and modern MLX blocks with minimized framework crossings. MLX's
current interop documentation describes shared Metal-buffer DLPack imports
where supported, with private-buffer copies otherwise. It explicitly requires
producer synchronization. Verify the exact version pair, buffer lifetime,
strides, dtype and concurrent stream ordering; unified memory is not automatic
zero-copy execution. Moving a larger block into one framework may avoid more
overhead than optimizing individual conversions.
[MLX interoperability](https://ml-explore.github.io/mlx/build/html/usage/numpy.html).

OpenFold residency needs a real model-owning adapter and verified request-level
state reset/checkpointing. Its previous queue failure was an unsupported
scheduler request. Do not merely enable the existing resident flag. Keep
PDE/confidence outputs correctly identified; an optimization cannot turn PDE
into PAE or justify computing ipSAE from it.

### E. Tune shapes and memory by workload

IntelliFold currently pads mixed-length inputs to a campaign bucket. Compare
that with a short declared bucket set and exact lengths, including compile
warm-up and peak memory. Every padded token/atom needs correct masking and
unpadding. A directory of Boltz/Protenix inputs is primarily model-load
amortization, not necessarily a simultaneous tensor batch. Do not count it as
dense batching or split it into extra model loads without evidence.

Benchmark chunk sizes, native sample batch widths and cache limits against
token count, atom count, MSA depth, chain topology and guidance mode. RFD3 already
has an explicit cache limit and generation width; measure alternatives instead
of inheriting one workstation's setting. A high-core-count chip with little
available memory can need smaller batches than an older high-memory machine.

Do not enable global fast math, CPU fallback, unlimited memory watermarks or
aggressive concurrency as a general fix. `PYTORCH_MPS_PREFER_METAL` is a narrow
matmul-path experiment; record its effect rather than assuming it helps every
operation. [PyTorch MPS controls](https://docs.pytorch.org/docs/2.14/mps_environment_variables.html).

### F. Mixed precision and specialized hardware, after equivalence work

Start with the currently validated precision per model. Then separately test
selected BF16/FP16 matrix operations with stable reductions, normalization,
softmax, geometry, diffusion accumulation and scoring retained at sufficient
precision. RFD3 already uses a mixed/BF16 production profile, so its baseline
must not be described as all-FP32. Record weight, activation, accumulator and
output dtypes independently.

M5 matrix acceleration is promising where the actual shapes qualify. An M5
profile must pass the same numerical acceptance as the generic one. Quantizing
weights to int8/int4/FP8, changing model variants, reducing diffusion steps,
recycles/MSA depth, disabling potentials, altering beam/early-stop rules or
using NESSO to replace more folds are separate scientific changes. They are not
part of the primary equivalent-throughput comparison.

## 4. Benchmark design

### Freeze inputs, baselines and ownership

Use a versioned benign fixture set: monomers such as ubiquitin/SUMO, ordinary
multichain examples, representative antibody frameworks, and small-molecule
examples with complete atom identity. Include short/medium/long token classes,
shallow/deep fixed MSAs, odd shapes, multiple chains, and both template/no-template
paths where supported. Keep every input/MSA/template/model hash in the manifest.
Avoid a benchmark made exclusively of easy short structures.

Profile mathematical tensors first, then a bounded 1–5-output end-to-end smoke
run for each new engine/configuration before larger work. The proposed suite
must be manifested under `Validation/experiments/`, with immutable raw output,
output audits and entries in both Lab Books. This document is not an executable
scientific plan and has not allocated jobs or fixture identities.

All expensive execution must use the bridge's immutable plan and `job_start`,
with the shared execution lock and recorded scheduler. Isolated candidate
runtime roots and measurement options must become explicit plan fields with
source hashes; if the current schema cannot express them, extend and test it
before launching. Never replace a live venv or bypass preflight to benchmark.

The existing `calibrate_device_throughput.py` imports
`benchmark_sumo_predictors`, which is absent from the inspected shipped scripts.
The existing profile identity also covers only a subset of engines and includes
hostname. Reuse its useful workload/memory concepts, but repair packaging and
extend provenance before calling it the all-engine benchmark harness.

### Measure three levels

| Level | Question | Measurements |
|---|---|---|
| Operator/block replay | Why would this improve performance? | Actual dispatch, tensor shapes/strides, wall/device time, copied bytes, allocations, synchronization, output error |
| Fixed-input prediction | Is the same model/protocol faster? | Cold start, model load, feature prep, trunk, diffusion, guidance, confidence/affinity, serialization/audit, peak memory |
| Real workflow | Does a user finish earlier? | Total wall time, all required outputs, CPU stages, model switches, queue waits, failure/retry costs, checkpoint/resume |

Use Instruments/Metal traces and PyTorch MPS signposts for profiling. Generic
CPU operator timing alone cannot establish GPU time. Trace with synchronization
only where needed; disabling asynchronous behavior can change performance.
Use an unprofiled run for the headline timing.
[PyTorch MPS profiler](https://docs.pytorch.org/docs/2.14/generated/torch.mps.profiler.profile.html).

At timed boundaries synchronize MPS; force MLX outputs to evaluate and finish.
Otherwise a measurement can capture graph construction/enqueue rather than
completed inference. Avoid a synchronization after every kernel in throughput
runs. For combined-framework work finish both producers/consumers correctly.

Record cold process launch, first shape execution, and warmed steady state
separately. Distinguish fresh-process from empty OS shader/file cache; restarting
Python does not clear all caches. Include compilation amortization and determine
the break-even job count from measured compile cost and per-item savings.

### Replication and statistics

Initial screen: three independent process blocks, interleaving baseline and
candidate order; record the first call and at least three warmed repeats on a
small matched fixture set. This is a rejection screen, not broad acceptance.
Estimate variance and runtime from it before fixing the confirmation budget.

For promising candidates, start confirmation with 12 diverse fixture inputs,
four fixed seeds per applicable stochastic model and three interleaved blocks;
freeze the final count and equivalence margins before examining candidate
confirmation results. Smaller resource budgets must be explicitly labelled
exploratory. Extend coverage/power where rare failures or noisy timing require
it. Keep an independent holdout set for final promotion after tuning.

Compute paired runtime ratios for identical work. Report per-workload results,
median latency, aggregate completed outputs/hour, tail latency where adequately
sampled, and confidence intervals resampling independent inputs/process blocks.
Do not treat diffusion steps, atoms, or correlated design cycles as independent
replicates. Keep every failure in the table; do not silently omit slow/OOM arms.
If an arm fails required work, it does not qualify for a speedup claim.

For iterative campaigns, include cycle 00 time in total elapsed time and label
it separately from optimized-output counts. Report seconds per prediction as
well as end-to-end seconds per completed requested unit; define the denominator.
Use the same complete protocol and fixture mix on each side. Freeze cache state
and show preprocessing-cache hits separately so warm caches cannot masquerade
as GPU improvements.

Log chip/device name, GPU family/core information when available, RAM, OS build,
power mode/AC status, thermal state, package/adapter hashes, effective environment,
precision, seeds, shape/chunk/batch policy and memory pressure. Measure sustained
blocks; alternate arms to reduce thermal drift. Do not sum overlapping MPS/MLX
allocator counters as if they were independent physical RAM. Include process
footprint, system pressure and swap alongside framework counters.

### Numerical and functional acceptance

There are two references: the existing production baseline, and an independently
checked numerical reference. The former can itself contain a bug. Use CPU
FP64 for small mathematical cases where supported, CPU FP32/upstream oracle
outputs for model blocks, and explicit strict arithmetic on GPU. A candidate
that fixes a baseline defect needs its own correctness decision.

1. **Exact contracts:** shapes, masks, atom/token/chain identity, output counts,
   checkpoint bytes, seed mapping, fixed regions, restraints and file fields.
   Missing, duplicated or reassigned outputs fail.
2. **Operator equivalence:** absolute and relative error distributions, maximum
   outliers and normalized residuals against reference. Test masked/empty rows,
   singular alignments, long reductions, extreme magnitudes, odd strides,
   expanded sample dimensions and memory reuse. Test gradients where a guided
   inference path needs them; `inference_mode` is not a universal replacement.
3. **Block equivalence:** captured inputs for attention, triangle updates,
   denoiser outputs, confidence/affinity heads and embeddings. Compare the same
   inputs at multiple stages. Sampling decisions need logits/probabilities and
   fixed decoder histories; final sampled sequences alone are insufficient.
4. **Trajectory checks:** where possible supply identical captured noise/RNG
   state and compare denoiser steps before feedback amplifies differences.
   Equal seed integers across libraries/batching do not guarantee equal random
   draws. When backend RNG differs, keep the deterministic block comparison
   and additionally run a matched ensemble assessment.
5. **End-to-end correctness:** finite complete coordinates, geometry invariants,
   aligned coordinate differences with consistent atom mapping, pair-distance
   residuals, per-residue confidence and pair-error matrices, affinity and
   interface-score changes, and decision changes near established thresholds.
   Higher predicted confidence is not proof of accuracy; retain suitable
   experimental/upstream-reference structure checks. Evaluate tails, not only
   average scores or correlation. Preserve PAE/PDE distinctions.
6. **Operational acceptance:** cancellation, worker death, sleep/wake, restart,
   resume, repeated varied shapes, long-lived allocator stress and memory soak.
   Resume must reuse audited completed units and the exact original profile.

No universal `allclose` tolerance proves all these models correct. Proposed
engineering screening thresholds for well-scaled FP32 primitives can begin
with `atol=1e-5, rtol=1e-4`, supplemented by residual/condition-number tests;
these are not scientific acceptance thresholds. Establish model/block-specific
limits from reference accuracy and baseline variation, prespecify them before
candidate confirmation, and do not loosen them simply to make an arm pass.
Mixed-precision profiles require their own prespecified limits and evidence.
[PyTorch numerical accuracy guidance](https://docs.pytorch.org/docs/2.14/notes/numerical_accuracy.html).

Proposed performance promotion rule: all numerical/functional gates pass; the
paired 95% interval excludes slowdown for the advertised workload; an engineering
target of at least 10% median end-to-end improvement justifies a new specialized
profile. The 10% is a proposed maintenance threshold, not a measured result.
Smaller simple upstream improvements or memory-only benefits can be worthwhile,
but describe them honestly and avoid a universal speed claim. Correctness
failures block promotion regardless of speed.

## 5. M1–M5 and future-device selection

**Detect capabilities, then choose a validated profile.** Chip generation is
one input, not the whole decision. Probe Metal device/family support, runtime
availability, exact OS build, dtype/kernel capability, usable memory and the
workload signature. A tiny installed-runtime self-test checks compatibility;
it cannot certify an untested model or replace full validation.
[Metal device families](https://developer.apple.com/documentation/metal/mtldevice/supportsfamily(_:)),
[recommended working set](https://developer.apple.com/documentation/metal/mtldevice/recommendedmaxworkingsetsize).

| Validation hardware | Required role |
|---|---|
| M1, including a low-memory configuration and the previously affected M1 Pro class | Baseline compatibility, allocator/index correctness, bounded-memory behavior |
| M2 | Physical compatibility/precision/dispatch acceptance; representative mixed workloads |
| M3 | Same acceptance, including its actual OS/runtime combinations |
| M4 Max reference workstation | Development profiling, full benchmark matrix and memory soak |
| M5 base and a Pro/Max-class device where accessible | Matrix-accelerator benefit and numerical parity; memory/bandwidth variation |
| Fanless laptop and low-memory 8/16-GB tiers represented across the fleet | Sustained thermal and memory-constrained operation, not just short workstation timings |

Run the generic smoke/accuracy suite on at least one physical device from each
generation before advertising that coverage. Full performance sweeps can focus
on M1/M4/M5 initially, with targeted confirmation on M2/M3. Record untested
chip/OS combinations explicitly. A 64-GB M4 result is not M1/M5 evidence. Cover
the declared minimum OS, current supported OS, and the 26.2 capability boundary
where installable. Future chips cannot be pre-certified.

Supporting an M1 does not mean every giant input fits every 8-GB Mac. Define
per-engine memory envelopes and explain incompatible workloads before starting;
do not silently reduce samples, crop inputs or choose a smaller checkpoint.

The signed engine catalog should associate a runtime/adapter revision with a
small set of validated execution profiles: conservative baseline, tested
throughput profile, bounded-memory profile, and specialized tensor-kernel
profile where useful. Each specifies numerical policy, minimum OS/capabilities,
supported shapes, chunks/batches, memory limits, compiler/kernel versions,
validation evidence and known exclusions. These are conceptual categories,
not profiles implemented by this task.

Select automatically before preflight freezes the job, explaining simply
“Optimized for this Mac” with details available. Preserve the profile ID and
full dependency graph in every plan/result. If no specialization matches, choose
the documented compatible baseline and record the reason. This is explicit
execution selection, never a silent substitution of scientific settings.

After a device/OS/runtime change, invalidate stale calibration. For an unknown
future chip, offer the capability-compatible baseline only after compatibility
checks, label performance as unvalidated, and wait for release validation before
enabling a specialized path. A job already frozen to another profile must fail
clearly or require an explicit new plan; do not silently adapt its arithmetic.
OOM recovery likewise must preserve sample identities and recorded policy.

Avoid one full download for every M-number. Share an arm64 runtime where
compatible and dispatch kernels by capability; split runtime payloads only when
OS/dependency requirements demand it. Deliver prebuilt native components and
supported shader assets through immutable signed GitHub Releases. Verify the
selected profile works on a clean Mac without CLT: compiler/JIT experiments
must not reintroduce a developer-tool requirement. Normal OS Metal shader
compilation and external C++/SDK compilation are different dependencies.

## 6. Proposed work packages and exit criteria

| Order | Work package | Exit evidence |
|---|---|---|
| 1 | Repair/extend benchmark harness, freeze generic fixtures and provenance | Managed plan can express baseline/candidate runtime; scripts ship complete; audit/replay and failure fixtures pass |
| 2 | Profile production versions and test isolated Torch/MLX upgrades | Per-engine compatibility table, stage traces, paired same-settings results, independent numerical references |
| 3 | Test preprocessing reuse, NESSO ESM simplification, IntelliFold buckets and scheduler choices | Individual contrasts followed by combined-candidate replay; end-to-end gain survives memory/thermal tests |
| 4 | Resolve OpenFold dispatch and compare native MPS / MLX interop; prototype supported residency | Actual device/kernel evidence, no stale per-request state, interop lifetime/stream tests and full output parity |
| 5 | Fuse proven attention/triangle/sparse hot blocks; evaluate selective compilation | Oracle-tested blocks, cold/warm break-even, exact mask/neighborhood behavior, generic fallback |
| 6 | Validate optional mixed-precision/M5 profiles and fleet coverage | Physical M1–M5 matrix, explicit precision acceptance, soak and interruption results |
| 7 | Publish only passing immutable profiles, gradual rollout and rollback | Clean-Mac install, compatible automatic selection, pinned old jobs, no model-weight redistribution |

Stop an experiment when it fails correctness, has insufficient memory, or does
not improve the real workload after overhead. Use measured stage fractions to
prioritize the next experiment: improving a tiny fraction of runtime has a
small upper bound on total benefit. Report negative results as well as winners.
Re-test combinations; isolated gains do not multiply automatically.

No speedup or delivery-time forecast is defensible before the baseline traces.
The immediate implementation target is a complete, trustworthy harness and an
isolated same-settings Boltz runtime comparison, followed by IntelliFold,
Protenix and the MLX port. MPNN CPU execution remains unchanged.
