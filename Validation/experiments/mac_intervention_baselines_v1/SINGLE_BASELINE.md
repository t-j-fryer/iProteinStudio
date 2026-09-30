# One practical baseline per model

2026-09-30. Supersedes the three-stage figure proposal in RESEARCH.md, following the user's clarification. Research only; no new predictions. The earlier source/history audit remains useful supporting material.

## The comparison

**Baseline = the developer implementation, or the community Mac port we actually adopted, before our optional performance interventions. Optimized = the same checkpoint/scientific task with the qualified Studio interventions.**

Use one baseline per model, not an author-versus-community-versus-Studio ladder. Retain upstream native reuse/batching; do not force repeated model loads. A thin, identical input/output/timing adapter may feed both arms. Necessary device/dtype/unsupported-operation fixes must be disclosed where an author implementation has no working Mac route; call that baseline “upstream + minimal MPS compatibility,” not unmodified. Such shared compatibility fixes are credited in the methods, not assigned a fictitious speedup.

Freeze the historical runtime used before our optimization programme when that runtime has a valid Mac control: this intentionally includes the qualified Torch upgrade in the combined Studio intervention. Those historical runtime choices are not claimed to be mandatory upstream versions. Community source stays on the SAME commit in both arms; using an old broken community release would exaggerate our contribution.

## Exact baseline choices and optimized endpoints

| Model | Single baseline | Combined optimized arm |
|---|---|---|
| Boltz2 | Developer Boltz2.2.1; historical Torch2.13.0; minimal FP32/MPS correctness wrapper and counted required SVD handling retained; original preparation/device lifecycle | Same model/FP32/correctness wrapper; Torch2.14.0 and continuous MPS residency |
| IntelliFold Flash | Developer PyTorch source4e420db7482b4f50dbb86800ff710ee4ec7c7b7b; historical Torch2.6.0; FP32/MPS; original256+ token buckets, native per-request CCD load | Torch2.14.0; exact tokens; immutable CCD retained between calls |
| IntelliFold Full | Same pinned source/Torch2.6.0 and original buckets; Full checkpoint | Torch2.14.0; exact tokens; retained CCD. Include despite exclusion from the ongoing large campaign because it is a distinct app model and a major padding case |
| OpenFold3 | Community latent-spacecraft/openfold-3-mlx at eeac37eb82dc2b80cf043eb26105a16d2493d052; Torch2.6.0/MLX0.32.0; native10-worker loader, initializer and device lifecycle; correct MSA filenames in both arms | Same runtime/checkpoint; zero workers with native feature RNG preserved, continuous MPS residency and direct RDKit coordinate arrays. Keep initialization shortcut OUT of this endpoint: it is qualified separately but not part of the current selected campaign stack |
| Protenix v2 | Developer2.0.0 source4c355be4553512f72453ecbfb65e69f4c35d1413 + minimal FP32/MPS patch; Torch2.7.1; native chemistry cache and runner reuse retained | Qualified FP32/native model path. Do not include rejected Torch2.14, trunk BF16 or unhelpful cache combinations. A small/zero improvement is a valid outcome |
| Protenix Mini | Same developer source/runtime/MPS port; Mini's own checkpoint and native inference profile | Native qualified path. No presumed model-computation speedup; do not compare Mini against v2 as an intervention |
| Protenix Constraint | Same developer source/Torch2.7.1 + common MPS port, with configuration matched to the old learned checkpoint; original zero-substructure computation and original per-prediction cache policy | Verified dead-ESM-path removal where applicable, zero-substructure shortcut preserving learned biases, native diffusion-conditioning cache. Original large-complex arm may OOM; label it rather than substituting another baseline |
| ESMFold2 Full | Community faustomilletari/mlx-lm at c26b9af872158d822a8c95589708eedd3b9c0831; MLX0.32.2; native FP32 folding/BF16 ESMC; normal allocator policy; native loaded-model/builder reuse | SAME community backend/model computation, Studio integration and4GiB free-cache target. Exclude failed target-embedding cache |
| ESMFold2 Fast | Same community source/runtime; Fast checkpoint, sequence-only native50-step profile | Same computation with qualified allocator policy/integration. Do not claim Full-to-Fast or PyTorch-to-MLX as our speedup |

The Constraint checkpoint lacks a learned ESM projection, while later source initializes an extra projection to zero. If the chosen checkpoint-correct baseline already omits ESM, there is no dead-ESM saving to count. Record the exact configuration; never create artificial extra work to inflate the contrast. Native nonzero substructure inputs retain their upstream computation in both arms. The allocation shortcut is optional algebraic simplification rather than an MPS operator fix, so it belongs in the intervention, even if the baseline cannot fit a larger case.

Original packages/patch boundaries still need to be frozen into isolated baseline environments before execution. In particular, IntelliFold's public/current README describes JAX despite the pinned retained PyTorch runner; do not reconstruct that arm with a new unpinned `pip install intellifold`. No community/kernel work is attributed to Studio.

## Evidence already available

All numbers below are historical measurements on this M4 Max,40 GPU cores,64GB (macOS26.6.1 for the recent campaigns). They are not new measurements or one interchangeable benchmark set. Timings are seconds unless otherwise stated.

| Model/change | Existing speed evidence | Output evidence and scope |
|---|---|---|
| Boltz runtime upgrade | Torch2.13→2.14 reduced two-input time by7.08%,20.70%,0.11% in three paired process blocks (0168) | All measured gates passed; maximum aligned CA difference0.001577Å. Magnitude varied substantially |
| Boltz residency | SUMO96/128-row/25-step five-seed request medians3.710→2.454 (0229); changing-binder reversed-order confirmation median paired saving0.773, about5.4% (0230) | Five changing-binder pairs exactly equal in compared coordinates/confidence. Monomer percentage does not generalize to longer complexes |
| Flash padding/runtime | Original→128-token policy two short warmed requests93.352→44.879 (0170); later128→exact96 saves8–16% across six SUMO cells (0228). Torch upgrade screens also favorable, with variable magnitude (0169) | Padding outputs exact or extremely close; later maximum core-coordinate difference<0.000046Å. Torch changes RNG streams: matched-draw and MSA/core checks are separate evidence |
| Flash CCD cache | Changing-binder median paired request saving1.688, five pairs (0230) | Compared saved coordinates/confidence exactly equal |
| Full exact tokens | Warm no-MSA SUMO96/200-step medians253.791→30.706; four warm timing pairs, five seeds audited (0228) | Maximum paired core drift0.000013875Å. Historical control; impressive small-input effect, not whole-panel gain |
| Full CCD cache | Five within-session alternating seed pairs: median paired whole-request saving1.901, but2/5 slower; outside-model saving2.804 (0229) | Outputs exact. Compute drift prevents attributing the whole initial before/after difference to CCD |
| OpenFold loader/residency | SUMO96/128-row/25-step five-seed medians16.849→4.057,75.9% lower request time (0229) | Very small coordinate differences; unchanged core CA-lDDT, no additional geometry defects |
| OpenFold coordinate preparation | Additional changing-binder paired saving0.645, five pairs (0230) | All practical numerical gates pass. Earlier monomer test did not establish a material gain |
| OpenFold initialization, separate | Corrected MSA pair42.914→26.895 for whole prediction call, one measured pair after warmup (0171) | Core-pair RMSD0.000004Å, identical confidence scalars. Prototype excluded from main endpoint unless separately integrated/combined-qualified later |
| Protenix v2 | Recent invariant-cache/template/Metal trials gave no dependable full-request gain (0230) | Faster one-pair BF16 probe failed fixed confidence gate; excluded. Torch2.14 not promoted from limited MSA diagnostics |
| Mini | Recent inference-mode trial gave only a small unconfirmed difference (0230) | Native path retained. No established extra speed gain |
| Constraint empty-substructure | Formerly failing227-token complex completed after shortcut; original predicted allocation about39.6GB (0045/patch) | On actual MPS, explicit/shortcut tensors at2,8,16 tokens differed by at most9.54e-7. No paired full-request speed number established for this large-case repair |
| Constraint diffusion cache | Five changing-binder pairs, median paired saving0.517, all pairs faster (0230) | All practical gates pass. Small effect, not an order-of-magnitude claim |
| ESMFull/Fast allocator | Five pairs each exactly equal; driver allocation observed at16.55–16.58GiB Fast and16.68–16.74GiB Full versus earlier growth to35.90/39.73GiB (0230) | Cross-session memory observations, not causal speed evidence or universal peak limits. Embedding caches failed fidelity and remain excluded |

The earlier ESM PyTorch→MLX timing comparison now belongs only in background/attribution, because MLX is our chosen baseline. It cannot contribute to the summary figure's “our improvements” speedup.

The ongoing674-complex×8-engine campaign adds breadth, native timing records and integrity/geometry evidence for the optimized arm. It is **not** a paired baseline study, has one seed per complex, and is still incomplete; successful outputs alone do not demonstrate equivalence or experimental accuracy.

Existing reports: project0168/0169/0170/0171,0228/0229/0230; `Validation/output/paper_binder_matrix_v1/optimization_summary/REPORT.md`; exact SUMO matrix and resident-overhead raw analyses. Do not multiply separate historical ratios into a combined gain. The primary missing result is the complete baseline stack versus complete optimized stack in the same fresh workload/session design.

## One explicit comparison for the summary figure

**Question:** How much faster and more memory-efficient is predicting a stream of different binders against the same target using our implementation, at unchanged scientific settings, and what happens to the outputs?

Use the existing96-aa SUMO and five distinct64/98/117/135/150-aa binders. Primary complex workload:5 binders×5 seeds42–46 =25 measured predictions per arm/model. Add SUMO alone×5 seeds as a small shape-sensitivity inset, not the main headline. All9 models×2 arms×30 predictions =540 measured outputs, plus declared warmups. Start with one complete paired block as a feasibility/output audit before committing to the rest; retain failures.

Use128 target-MSA records and query-only binders. ESMFast remains sequence-only. **Native diffusion budgets in BOTH arms**:200 for Boltz/IntelliFold/OpenFold/Protenixv2/Constraint,5 for Mini,100 for ESMFull and50 for Fast. Native recycles/loops retained, one sample; same checkpoints, precision, guidance and model inputs within each pair. For this protein-only benchmark Boltz potentials remain off in both arms, matching the recent benchmark. Record actual native iterations as well as requested steps. Native budgets avoid reduced-profile geometry defects and make the headline easier to interpret; existing reduced-budget tests already support the mechanistic explanation.

Organize into five independent process/session blocks per arm: each block predicts all five binders at one seed, with a fixed excluded warmup on each arm. Counterbalance arm order and binder order across blocks. Let the baseline use its native same-process/directory reuse; a resident API is not required if it does not exist. Submit all inputs without artificial wait, and do not charge baseline an avoidable reload per design. Save per-output completion times and block elapsed wall time, so writer buffering/prefetch cannot create a misleading per-request timing. Match preprocessing work and output products, or report unavoidable product differences explicitly.

**Main figure:** one model row, baseline and optimized paired summaries. Left panel: amortized warm end-to-end seconds per complex, from the five binder blocks, plus speed ratio and peak memory annotation. Middle panel: cold initialization separately and the monomer timing inset, so load savings and small-input padding gains are visible without dominating the complex result. Right panel: quality effect—paired interface-confidence changes where comparable, target-core RMSD to3QHT, binder geometry and baseline/optimized coordinate drift. Report medians and block-level uncertainty; five blocks provide descriptive, limited uncertainty, not strong population estimates. Inputs are a small SUMO case study; use the ongoing multi-target campaign as supporting breadth rather than claim universal generalization.

SUMO comparison uses residues21–96. After target-core alignment, assess binder displacement and geometry too. Agreement with the SUMO experimental structure says nothing by itself about binding correctness;3QHT is a bound experimental reference, not a designed-complex ground truth. Across Torch versions equal seeds can produce different random draws, so numerical equality is only demanded where RNG pathways match. Reuse existing matched-draw diagnostics as supporting evidence; primary science-quality distributions and failures remain visible.

If Constraint's unchanged baseline OOMs, report that cell as OOM, with no invented speed ratio. Do not replace it with a different convenient baseline. If v2/Mini/ESM show little speed gain, retain that result; memory, portability or correctness may be the actual benefit.

## Other tool families

If the figure expands beyond structure prediction, give these their own task labels and units: NESSO baseline=original working MPS scorer, after=AA/exact-conformer caches with five recycles fixed (0170:18.320→2.732 for two warm short requests, exact broader24-output checks); PSICHIC baseline=working author CPU pipeline, after=safe MPS ESM batch8+CPU graph scoring (0173:7.978→1.887 seconds/64 sequences, two opposite-order passes, rank/top8 preserved); RFdiffusion3 baseline=community javierbq/rfd3-mlx, with no credited custom-kernel boost because our trials failed quality or confirmation. Leave MPNN on CPU as requested. These figures are on the same M4 Max but different workloads/timing boundaries and must not share a “seconds per protein prediction” axis.

No inference, installs, active-job changes or production promotion were performed for this revision. Existing evidence hashes remain in evidence.json. Reconstructing clean historical dependency/patch stacks and freezing per-arm configuration are preparation tasks before a later authorized execution, not a need to repeat all the individual exploratory tests.
