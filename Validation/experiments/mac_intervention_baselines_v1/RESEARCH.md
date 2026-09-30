# Reconstructing Mac baselines for an intervention figure

Research date: 2026-09-30. **Research/protocol only; no new installations or predictions.** Ongoing paper-binder predictions were left untouched. Scope: the nine structure predictors in the SUMO matrix, with separate suggestions for design/scoring tools. This is not a completed before/after benchmark.

> The figure proposal below is superseded by [the single-baseline protocol](SINGLE_BASELINE.md). Source-history findings remain supporting evidence.

## Recommendation

Use three stages, with community ports explicitly credited:

1. **Author upstream:** pinned original model implementation and checkpoint, no Studio patches. Try documented configuration options before modifying code. Record install failure, unsupported operation, CPU execution, out-of-memory, invalid output, or successful GPU execution separately.
2. **Working Mac baseline:** the smallest demonstrably correct Mac implementation, retaining original inference work and avoidable overhead. Where this uses a community port, identify that port rather than attributing its implementation to Studio.
3. **Studio optimized:** the same model, checkpoint and scientific workload with our qualified changes. Distinguish the released implementation from newer isolated campaign optimizations.

The useful speed ratio is stage 2 / stage 3. Stage 1 establishes what became possible. A failed upstream execution has no valid speedup denominator. A working CPU implementation can have a separately labelled CPU-to-GPU comparison; it is not a GPU software-optimization comparison.

The four older local repositories are historical evidence, **not untouched upstream controls**. They already contain Apple-device adapters, alternative backends, padding changes or batching policies. Repository HEAD alone also misses uncommitted historical experiments. `evidence.json` records repository identities and selected source-file hashes; it does not certify a clean historical checkout.

## Engine reconstruction

### Boltz-2

**Author source:** `jwohlwend/boltz`, package/tag 2.2.1; use the same `boltz2_conf.ckpt` as Studio. The pinned source requests BF16 mixed precision for Boltz-2, provides CPU/GPU selection and a `--no_kernels` option. Do not label it universally CUDA-only: Lightning's GPU selection and installed dependencies must be checked on the actual Mac. The unmodified default and a documented-options-only Mac attempt are separate feasibility observations. [Pinned entry point](https://github.com/jwohlwend/boltz/blob/v2.2.1/src/boltz/main.py).

**Working Mac baseline:** native MPS, FP32, compatible attention/operator path; no silent general CPU fallback. Explicitly count and time the documented small SVD CPU operation where used. Retain the correctness allocator boundary when the chosen Torch runtime needs it. Removing a correctness fix to obtain a faster control is not acceptable. Native directory inference already loads the model once for a directory; preserve that capability in its baseline.

**Studio:** installed Torch 2.14.0; `scripts/boltz_mps.py` enforces FP32, explicit MPS, verified local assets, allocator boundary and output checks. Resident orchestration reuses the loaded model. The current paper campaign additionally keeps it on MPS between requests; that latter hook is campaign-only. Deterministic whole-input reuse and alternate Metal dispatch did not establish further useful gains for changing binders.

**Ablations:** qualified historical Torch versus 2.14; singleton versus upstream directory versus later-arriving resident requests; device residency on/off with all correctness checks held fixed. Hold potentials, affinity head, MSA subsampling, samples and diffusion work constant. The standalone and resident MSA flags have historically differed, so compare actual model-entry features, not just YAML filenames.

### IntelliFold Full and Flash

**Author source:** pinned PyTorch runner at `IntelliGen-AI/IntelliFold` commit `4e420db7482b4f50dbb86800ff710ee4ec7c7b7b`, each with its own checkpoint. The packaged source uses Accelerate device selection, CLI BF16 default and token buckets starting at 256. It is not established here that stock execution must fail on every Mac: FP32 is an exposed option, and Accelerate may select MPS. Test the actual runner before classifying feasibility.

**Important provenance trap:** the current public README, and even the README bundled alongside this installed PyTorch runner, advertise a JAX/AlphaFold3 distribution. A new `pip install intellifold` is therefore not an adequate reconstruction of our PyTorch baseline. The old pinned web file was unavailable during this review; use the preserved source and reverse/check the recorded patches against an independently obtained upstream archive before execution. Do not silently substitute the JAX implementation. [Current upstream documentation](https://github.com/IntelliGen-AI/IntelliFold).

**Working Mac baseline:** FP32/MPS with only required compatibility changes; original token buckets, native CPU preparation and fresh CCD loading retained. The patch also exposes bucket configuration through collation, changes CUDA-only cache cleanup and avoids unsupported pinned host memory. These changes should be separated by purpose rather than described as one kernel optimization.

**Studio:** installed Torch 2.14.0, exact token sizing for both models through the existing overflow calculation and bucket `1`; native internal atom/block padding remains. Old explicit bucket requests remain reproducible. The active Flash paper arm additionally retains the immutable chemical-component dictionary across requests. Full's CCD cache has experimental evidence but is not in the active paper campaign, which excludes Full.

**Ablations:** original 256+ buckets → exact length; historical qualified Torch → 2.14; CCD load each call → retained CCD. Full and Flash are separate model rows. Do not count Full → Flash as an implementation improvement. Small inputs will benefit disproportionately from removing padding; include inputs above original bucket boundaries too.

### Protenix v2 and Mini

**Author source:** `bytedance/Protenix` 2.0.0, commit `4c355be4553512f72453ecbfb65e69f4c35d1413`. Its runner selects CUDA when present and **CPU otherwise**, not MPS; CUDA-specific fast normalization/attention options also matter. This is a source-derived device conclusion, not a freshly executed CPU benchmark. [Pinned runner](https://github.com/bytedance/Protenix/blob/4c355be4553512f72453ecbfb65e69f4c35d1413/runner/inference.py).

**Working Mac baseline:** MPS device selection, FP32, PyTorch attention/layer normalization, confidence dtype fix, device-aware allocator calls and guarded CUDA imports. Strict checkpoint loading and explicit rejection of silent fallback are correctness/reproducibility measures. Preserve native cached CCD/component preparation and inference-runner reuse already supplied upstream.

**Studio:** both variants actually use installed **Torch 2.7.1**, not 2.14. Installed package metadata and lockfiles agree. Earlier runtime trials did not justify promotion for these engines. The active campaign keeps the qualified FP32 path; native diffusion-cache/template variants gave no reliable whole-request improvement for v2. A faster v2 trunk-BF16 probe failed the fixed confidence-change gate. Mini stays on its native path.

**Ablations:** CPU reference if feasible versus minimal MPS port (hardware-enablement contrast); then original invocation lifecycle versus resident execution. There may be little remaining optimization-only gain because upstream preparation is already efficient. It is scientifically useful to show that result. Mini's distilled checkpoint is a different model, not a speed intervention on v2.

### Protenix Constraint

**Author source/checkpoint:** same source pin, `protenix_base_constraint_v0.5.0`, SHA256 `5358025b20b2212853ad75579be04387859557915f398a1d60f6a1a9a0c8c887`. Besides the common MPS changes, two historical issues need separate treatment.

* The old checkpoint has no learned ESM projection; newer source initialized that extra projection to zero. Studio disables this mathematically dead branch and strictly verifies the checkpoint/configuration match. This is **not** permission to remove a nonzero learned ESM feature in another model. Compare against both checkpoint-era source and the later mixed-era source before calling avoided ESM computation an optimization.
* An absent substructure constraint becomes an all-zero token-pair feature. Upstream flattens it to a sequence of length N², giving an N⁴ attention allocation. Our patch evaluates the identical token once and broadcasts the learned result, preserving biases and the native nonzero-constraint path. Project entry 0045 records small-size numerical validation and successful completion of the formerly failing 227-token input. This belongs in both the capability/memory panel and a matched feasible-size ablation.

**Studio:** Torch 2.7.1, FP32 MPS, dead-branch/configuration correction and zero-substructure patch. The paper campaign additionally enables the native per-prediction diffusion shared-conditioning cache; this is not a cache of learned features across different binders. Qualify nonzero constraints separately before extending that campaign conclusion.

### OpenFold3

**Author upstream and community port are distinct controls.** The app uses `latent-spacecraft/openfold-3-mlx` commit `eeac37eb82dc2b80cf043eb26105a16d2493d052`, based on OpenFold3-preview, with checkpoint `of3_ft3_v1.pt` (SHA256 `aedd8f3eb814e3926c8974ef34c9499df224443f173b7e396c97684da6e3eeb6`). Determine the corresponding author-repository ancestor before constructing the original-author arm; current `aqlaboratory/openfold-3` main is not necessarily that model/version. [Author repository](https://github.com/aqlaboratory/openfold-3), [community Apple port](https://github.com/latent-spacecraft/openfold-3-mlx).

**Working Mac baseline:** unmodified community hybrid Torch/MLX prediction route with its native loaders and checkpoint. Credit the community's attention/triangle work separately. The port README's claims about Neural Engine execution are not evidence that our measured kernels use the ANE; our execution evidence is MPS/MLX GPU. Public README timing claims are not reused as our controls.

**Studio:** installed Torch 2.6.0 and MLX 0.32.0; corrected input mapping places target MSA bytes in a recognized `colabfold_main.a3m` slot. An earlier benchmark bypassed this production adapter and failed; that failure is not proof that upstream cannot consume MSAs. The active campaign additionally uses zero loader workers with native feature RNG preserved, continuous MPS residency, and efficient RDKit coordinate conversion. These changes are isolated hooks, not general installed defaults.

**Separate cold-start candidate:** skipping only initialization subsequently overwritten by strictly verified checkpoint loading was qualified in entry 0171 but was not promoted. Treat it as an additional candidate, not part of the current campaign's measured endpoint. Keep Torch2.14 out of the optimized arm until it passes the required quality validation.

### ESMFold2 Full and Fast

**Author baseline:** Biohub ESM PyTorch implementation. Historical pinned source is `43ccece2ad485f27db46afdb67da2a9601e8f106` plus its Transformers fork `ef32577f55da19a4989cd7b22e004dc43a4998cb`; independently resolve the Fast checkpoint/source compatibility too. Author examples use CUDA. The historical Mac experiment required MPS operator replacements, explicit small CPU SVD handling, RNG handling and dependency isolation; it is already a port, not stock. Direct BF16 loading of the ESMC weights avoids a large unnecessary FP32 transient. [Author usage](https://github.com/biohub/esm).

**Intermediate baseline:** the minimally patched PyTorch/MPS reference, followed by the independently authored MLX implementation. Studio's MLX source is `faustomilletari/mlx-lm` commit `c26b9af872158d822a8c95589708eedd3b9c0831`, MLX0.32.2; Torch2.11 remains in its supporting environment. [Community implementation PR](https://github.com/ml-explore/mlx-lm/pull/1484).

**Studio/current campaign:** FP32 folding, BF16 ESMC, resident builder/models, exact tokens and explicit native output audits. The campaign adds a 4GiB free allocator-cache target, which is not a 4GiB model-memory limit. It retained outputs in the tested pairs; the available cross-session evidence is a memory comparison, not a causal speed contrast. Target-chain embedding reuse failed fidelity and is excluded.

**Crucial limitation:** PyTorch → MLX is an operational backend comparison. Differences in masking, per-loop conditioning and random-number handling mean it is not proven arithmetic-only parity. Entry 0211's SUMO comparison had about 0.98Å between-backend core drift despite plausible structures from both. Plot quality beside speed and attribute community work. Full → Fast and reduced diffusion are separate scientific comparisons, never optimization ablations.

## What is already measured, and what those measurements mean

These are **historical local measurements**, not results of the proposed experiment. All below were measured on this M4 Max, 40 GPU cores, 64GB; see linked records for settings, raw outputs and limitations.

| Intervention | Existing evidence | Appropriate interpretation |
|---|---|---|
| IntelliFold Full padding | Warm no-MSA SUMO96/200-step request medians 253.79 → 30.71s; four warm pairs, five seeds audited; maximum paired core drift <0.000014Å (project 0228) | Strong candidate; earlier/later controls, small target; not a whole-panel causal estimate |
| OpenFold loader/device lifecycle | 16.849 → 4.057s resident median; five seeds, SUMO96/128-row/25-step (0229) | Minimal port already present in control; not original-author versus Studio |
| Boltz residency, changing binders | Median paired saving 0.773s in reversed-order confirmation; five different SUMO binders; exact compared outputs (0230) | Relevant changing-binder gain; smaller than repeated-small-input percentage |
| Flash CCD cache, changing binders | Median paired saving 1.688s; five different binders; exact compared outputs (0230) | Reusable chemistry benefits new sequences |
| Constraint native diffusion cache | Median paired saving 0.517s; five pairs pass practical numerical gates (0230) | Small measured extra gain, campaign-only |
| ESMFull PyTorch/MPS → MLX | Fresh model medians 9.881 → 5.002s (two fresh processes each); resident medians 11.318 → 6.719s (three calls each), SUMO96/full profile (0211) | Community backend comparison; semantic/coordinate differences; not our kernel-only speedup |

Do not multiply these ratios into a cumulative claim. Workloads, controls, runtime versions and timing boundaries differ. Even an unchanged OpenFold control moved from a 41.648s median to 13.123s across the recent experimental sessions; the cause was not established. Fresh counterbalanced controls are essential.

## Proposed execution protocol, when requested

* Freeze a new environment/source/patch/checkpoint manifest for each arm. Do not uninstall or reverse patches in the user's current environments. Read-only weight sharing is acceptable; output directories are distinct and immutable. Resolve missing original-author commit/environment pins before launch. A failed dependency installation is an observed feasibility result, not an invitation to relabel modified code as stock.
* Primary workload: SUMO96 monomer plus the five distinct existing SUMO binders (64,98,117,135,150 aa) to expose reusable target/chemistry work. Confirm benign inputs and exact sequence/MSA hashes from the existing manifests. Follow with a small prespecified multi-target/length panel sampled from the ongoing paper cohort. Choose representatives before inspecting new timing or structural outcomes.
* Primary matched speed profile: 128-row target MSA and the same reduced budget within each engine (25 steps for the 200-step engines; Mini1; ESMFull13; Fast retains its qualified sequence-only50-step profile). Clearly label this as the reduced-workload stratum. Run a smaller native-budget stratum too (200 / Mini5 / ESMFull100 / Fast50) before claiming the interventions generalize. Keep recycles, samples, precision, guidance and all input bytes fixed within each implementation comparison; record requested **and executed** native denoising iterations. Reduced-step geometry limitations remain visible.
* Use five seeds 42–46 per input, one sample per seed; repeat timings in at least three independent resident-session blocks, randomizing or counterbalancing arm order. Five different seeds alone do not measure machine/session variability. Within a framework, compare paired outputs. Across frameworks/runtime RNG changes, save/compare initial noise where practical and otherwise report distributional and experimental-reference agreement rather than demand seed-wise identity.
* Time separately: environment installation/download (capability appendix); fresh process/import/load/first prediction; native preknown directory batch; and later-arriving changing-binder resident requests. Let upstream use its own directory/model reuse. Do not manufacture a slow baseline by reloading each time when upstream supports reuse. Resident controls can use a thin explicitly labelled harness around upstream APIs, without adding caches or shape changes.
* Main performance measure: wall time from accepted input to atomically written, audited output. Report both engine-ready request time and full application latency if measured; keep queue wait separate. Partition imports/weight I/O, CPU parsing/MSA/CCD, feature construction, device placement, trunk/recycles, diffusion, confidence, writing/audit and teardown. Synchronize async GPU boundaries. Nested diagnostic timers are not additive; detailed profilers run separately from primary timing. Record peak live/driver memory, CPU thread/worker settings, fallbacks and model-load count.
* Correctness: exact requested sequences, complete backbone, finite coordinates/confidence, correct output cardinality, actual MSA consumption, strict learned-weight coverage and geometry checks first. Compare fixed SUMO core21–96 against 3QHT; also assess binder geometry and binder position after core alignment, interface confidence/PAE where available. The bound SUMO reference 3QHT validates target-core agreement, not the designed interface. Do not substitute pLDDT for experimental accuracy.
* For same-algorithm low-level changes, retain the existing practical paired screen: whole-complex backbone RMSD ≤0.1Å; binder CA RMSD after core alignment ≤0.2Å; normalized confidence/per-residue pLDDT changes ≤0.01; mean PAE/PDE error ≤0.1Å; no additional geometry defects. Report exact equality separately. These are implementation-fidelity screens, not validated wet-lab success thresholds. Cross-backend comparisons require a separate prespecified quality analysis and cannot be declared equivalent just because each fits one crystal similarly.
* Retain failed runs and rejected optimizations, use bounded memory/caches, verify cancellation/resume in the optimized lifecycle, and include a mixed-length soak before production promotion. Keep current prediction campaign priority and exclusive GPU scheduling intact.

## Proposed paper figure

**A — Execution capability and attribution.** Engine rows; author stock → working Mac/community port → Studio columns; mark CPU/GPU, failure stage, scientific validity and patch categories. Unsupported is labelled, never drawn as a zero-time bar.

**B — End-to-end time and memory.** Working-Mac versus optimized paired request distributions, with cold-load time and directory/resident throughput separately labelled. Show target lengths and MSA/profile. Use paired speed ratios per input; aggregate across inputs with uncertainty resampled at the input/session level, not thousands of correlated diffusion steps. A single huge padding benefit must not define the headline for all lengths.

**C — Quality preservation.** Paired core/interface/geometry metrics and between-implementation drift; mark exact outputs and failed gates. ESM backend changes receive a distinct symbol. Installation success and robustness belong alongside speed rather than being sold as kernel throughput.

Use the established transparent SVG/Arial/black-axis style. No numerical figure is generated now because the new paired arms have not been run.

## Other app tools: separate panels, not mixed with folding seconds

* **NESSO:** compare minimally correct MPS scoring with the current amino-acid/identical-ligand conformer caches. ESM batching can be a separately qualified arm; the downstream model has candidate-specific pocket indexing, so naive whole-model batching is invalid. Keep five recycles/refinement fixed; one-versus-five is a scientific scoring change. Entries0169/0171/0172 preserve the relevant evidence.
* **PSICHIC:** include upstream CPU scoring and corrected MPS ESM batch8 + CPU graph scoring. CPU graph execution is intentional. Safe token transfers fix a demonstrated source-buffer lifetime defect; a fast run producing sequence-independent embeddings is invalid. Entry0173 records the matched numerical/timing controls; experimental scientific status remains.
* **RFdiffusion3:** author implementation → independently authored `javierbq/rfd3-mlx` port → qualified Studio execution. Pin common checkpoint/guidance/noise. Credit the MLX port. Our custom Metal sampler proposal failed quality qualification, and a later SDPA control did not confirm a gain; neither belongs in the optimized endpoint (0169).
* **MPNN/AntiFold:** CPU operation is acceptable by user preference; include only workflow overhead/batching if useful. A GPU rewrite is not a prerequisite for this figure. Retired AF3/JAX or obsolete IntelliFold JAX experiments are historical context, not valid optimized controls.

## Evidence and remaining reconstruction work

Project records: 0002 (inherited history),0043/0045 (Constraint),0169/0171 (runtime/kernel qualification),0172/0173 (scorers),0208–0215 (ESMFold lineage),0225 (default audit),0228 (exact tokens),0229 (resident overhead),0230 (changing-binder campaign). Canonical scripts/patches and selected authorized historical sources are hashed in `evidence.json`. Existing campaign checkpoint hashes are referenced there without copying weights.

Unresolved before any runnable submission: reconstruct clean pinned IntelliFold source and its compatible historical dependency resolution; identify the OpenFold author ancestor; freeze stock baseline package locks; pin/verify each source/checkpoint combination including Fast; split minimal compatibility patches from optional performance edits; finalize the representative multi-target panel. Stock feasibility classifications are predictions from source unless a cited historical experiment actually observed them. No new before/after runtime, fresh-Mac acceptance, cross-chip result, kernel measurement or production promotion is claimed here.
