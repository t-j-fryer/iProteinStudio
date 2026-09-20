---
entry: 0169
title: Test other Apple engine runtimes
date: 2026-09-19
author: Codex
type: benchmark
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [predictors, performance, runtime]
---

## Context
Follow [0168](0168-test-isolated-apple-runtimes.md). User requests this Mac only,
all other engines, Torch 2.14 where applicable, no Protenix Mini. MPNN stays CPU.
Scientific settings, models, steps, guidance and sample counts remain fixed.

## What was done
Isolated experiment `Validation/experiments/apple_runtime_throughput_v2` and
outputs `Validation/output/apple_runtime_throughput_v2`. Runtime/source clones,
immutable plans and real Studio shared broker lease. Installed detection passed
before testing. Existing stopped biotin campaign is not restarted.

## Results
In progress. Initial screens on this M4 Max:
- IntelliFold Flash2.6→2.14: two measured inputs total95.539→78.112s (one process pair). All confidence/PAE and backbone checks pass, but CA RMSD1.277–1.288Å exceeds the prospective0.5Å gate. Generator diagnostic queued; no promotion.
- NESSO2.11→2.14:18.882→23.538s (one process pair). Embedding relative L2≈2e-6 and scalar changes<2e-5 pass. Warm network work is a small part of end-to-end latency; CPU CCD loading and fresh preprocessing-worker startup dominate the remainder. Confirmation/profile and ESM/CCD reuse arms queued.
-12 receipt/numerical tests pass. A separate CPU RDKit test proves cached molecules are cloned per request (mutating one request does not affect the next; one disk loader call for two requests). RFD3 first attempt failed before prediction due a harness version-string suffix; AntiFold first attempt failed on an empty-string light-chain field. Both corrected in new immutable plans, original attempts retained.
- IntelliFold Full warmup sampled for3s: MPS graph execution/submission and waiting OpenMP workers, not evidence of a large parallel CPU math stage. Current memory-pressure query reported67% free and no thermal/performance warning;13.6GB allocated swap is historical occupancy, not proof of active swapping. Warmup sampling artifact retained; warmup excluded from timing comparisons.
Raw receipts, source/runtime seals and all failures retained. Other engines still queued/running.

## Decision and rationale
Profile actual stage fractions before spending on CPU thread sweeps. Compare
Torch 2.14 per engine, and MLX separately for RFD3. No global pin change.

## Reproduce
`python3 Validation/experiments/apple_runtime_throughput_v2/prepare.py intellifold protenix constraint nesso openfold rfd3 antifold`
Plans, frozen code, package graphs, hashes and commands saved with each job.

## Limits and what was not tested
No fleet, release packaging, production promotion, long soak or full campaign
validation yet. Initial small single-sequence screen cannot certify all designs.

## Next
Complete comparisons, accuracy audit, stage profiles and measured conclusions.

### Interim diagnostic update (21:45 UTC)
- IntelliFold Full: measured two-input total 729.857→679.203s (6.94% less elapsed time); ubiquitin CA RMSD0.182Å passes, SUMO1.604Å fails. Confidence/PAE gates pass. Post hoc joint-pLDDT≥70 coordinate localization saved separately; it does not replace original gates.
- Direct MPS RNG probe proves Torch2.6 and2.14 produce different random draws for the same explicit generator seed/call shapes. Flash identical-draw replay queued; replay timings are diagnostic only.
- Flash profile SUMO44.488s: preprocessing4.369s, trunk23.749s, diffusion15.104s, confidence0.566s (nested model_total39.421s). Padding and1-vs4-thread arms already queued.
- AntiFold initial fixed-backbone logit screen passes (largest observed scalar logit difference under0.0003). Both-shape-warmed confirmation added because new-shape compilation dominates the first SUMO timing. This is not an antibody holdout.
- Constraint Torch2.7.1→2.14: measured total27.705→12.774s; original coordinate/PAE gates fail substantially. RNG diagnosis queued; upstream cache screened separately on baseline runtime. Audit parser was corrected for the upstream `token_pair_pae`/`token_pair_pde` field names; raw files and gates unchanged.
- Native FP32 OpenFold SDPA prototype prepared with existing Q scaling preserved (`scale=1`), broadcast/additive masks, independent FP64 oracle. Actual trajectory test waits for OpenFold screen/profile. No MLX-route performance claim without dispatch counters.
-17 CPU harness tests pass, including global/explicit-generator replay, restoration on failure and SDPA oracle/mask/precision checks.

### User-directed SUMO endpoint amendment and report review
User requested high-confidence SUMO core comparisons and review of Anthropic's
2026-09-17 biomolecular acceleration article/report. `analysis_policy.json` now
selects baseline CA pLDDT≥80 (minimum20 residues), aligns/scores the same indices
in the candidate, retains whole-chain geometry/confidence/error-matrix checks,
and saves the original whole-chain audits. Candidate confidence cannot shrink
the mask. Full IntelliFold SUMO core RMSD0.0829Å on73 residues now passes; Flash
SUMO core0.112Å also passes, while its ubiquitin difference required RNG replay.
The queued Full-only RNG replay was cancelled before inference as redundant.
Flash identical-draw replay passes both inputs (604 recorded/replayed draws per
input, all arrays identical; max CA RMSD0.0000593Å). Original seed-stream failures
remain visible, and replay-instrumented times are not used for speed claims.
20 CPU harness tests pass, including SUMO tail/core selection and candidate-mask
independence. An RFD3 fixture named sumo is only a length fixture and is explicitly
excluded from the SUMO-core rule.

Read the article, report methods and applicable engine/kernel sections, and
upstream optimization-kit change inventories. PDF (139 pages) and extracted text
are retained in ignored `output/apple_runtime_throughput_v2/research/`. A bounded
synthetic sparse-attention comparison (existing MLX, compiled MLX, MLX SDPA,
custom Metal with direct neighbor loads) is queued through the broker. It uses
an independent NumPy FP64 oracle, masked/irregular/repeated neighbors, declared
FP32/BF16 tolerances and alternating-order warmed timings. No model speed claim
will be made from an isolated operator benchmark.

A3s sample during the Protenix diagnostic startup found the main thread in dyld
library mapping/signature-registration `fcntl`, while other threads waited.
This interval is not evidence of parallel CPU compute that more threads would
accelerate. The separately profiled SUMO call took9.772s: model9.691s,
diffusion4.358s, confidence0.058s. Cold copied-runtime setup and steady inference
are reported separately.

### Profile-directed follow-up (22:09 UTC)
Flash padding128 versus256: two measured inputs100.582→45.101s, saved
coordinates/confidence/error matrices identical. A CPU-only reconstruction of
the exact saved upstream loaders confirms token tensors256→128 and pair tensors
256×256→128×128 (`padding_loader_audit.json`); this is feature-shape evidence,
not an additional timing replicate. Full's corresponding screen is running.
Constraint's baseline-runtime invariant cache passes (CA RMSD≤0.000009Å), but
27.705→27.138s against an earlier control is too small to establish a speed gain.

OpenFold's separate2.14 profile: SUMO37.477s, setup18.473s, model5.824s
(trunk1.046s, diffusion4.778s), zero MLX attention/conversion calls. A3s warmup
sample identifies SciPy truncated-normal initialization and idle Torch workers.
An isolated prototype skips only Linear LeCun/He initialization subsequently
overwritten by checkpoint loading; it requires strict loading, proves every
skipped tensor is a checkpointed parameter and equals the loaded value, and
blocks inference while coverage is incomplete.23 CPU tests pass including these
coverage failures. Actual OpenFold prototype execution awaits its audited screen.

OpenFold's saved CIF omits occupancy; Gemmi returns no models. The analysis now
uses Studio's existing raw atom-site reader explicitly for OpenFold and checks
sequence, atom identity, model/alternate-location contract, finite coordinates,
confidence and geometry. Adding occupancy only in an in-memory diagnostic
reconstructs one Gemmi model, confirming the parser incompatibility. Raw CIFs
are unchanged. Profile outputs now audit successfully.

The Protenix baseline SUMO fixture has no CA pLDDT≥80, so its high-confidence
core comparison is unassessable. It cannot pass and does not fall back to a
whole-chain coordinate gate. This limitation is kept distinct from arithmetic
drift; derived audits now also record their analysis-code SHA256.

### Padding, cache and thread screens (22:20 UTC)
Full IntelliFold padding128 passes: measured197.547s versus729.857s in the
earlier control (exploratory73% reduction, not a contemporaneous benchmark).
Max CA RMSD0.00000901Å. CPU loader replay independently verifies the actual
128-token dimensions for Full as for Flash.

NESSO CCD cache on2.14 passes:22.160→16.930s in a contemporaneous pair;
one CCD disk load services three requests with cloned mutable molecules.
The corresponding2.11 cache screen is queued. ESM-only arm cancelled before
inference because profile ESM0.08854/12.31889s gives a maximum0.72% payoff.

Flash thread choice depends on runtime: on2.6,4→1 threads91.741→78.857s
(one pair); on2.14, reversing arm order,4→1 threads45.410→51.536s.
Both output comparisons pass. These are exploratory process pairs, not stable
thread-count rankings; they contradict a universal "more cores" or "one thread"
rule. No additional thread grid is justified by the current profiles.

Protenix and Constraint2.7→2.14 generator probes produce different MPS normal
draws (first probe max absolute delta4.9133), matching the IntelliFold finding.
Identical-draw trajectory diagnostics are queued for both.

The first custom-kernel diagnostic executed three complete shape/dtype cases,
then stopped because the existing eager BF16 implementation's FP64-reference
relative L2 was0.0101912 atL128/K128/H4/d32, just above the declared0.01 limit.
The failed plan and partial measurements are retained. The next diagnostic keeps
the same thresholds and records finite oracle pass/fail per implementation
instead of aborting on the control's failure; nonfinite outputs still abort.
It addsL1064 (76×14 atom slots) before any model integration. Candidate failures
remain disqualifying; completion of the diagnostic is not itself an accuracy pass.

### Kernel and RNG outcomes (22:33 UTC)
The completed operator diagnostic passes all eight FP32/BF16 shape cases for
custom Metal and SDPA. Existing eager/compiled BF16 exceeds the independent
FP64-relative0.01 threshold at128/512/1064 slots; failures remain reported.
At1064 BF16 slots, median synchronized calls: compiled0.832ms, custom Metal
0.244ms (80 calls each, four alternating blocks). This is not model throughput.

Full RFD3 custom-Metal trial on existingMLX0.32.0: two measured outputs16.527s
versus27.192s earlier control;5373 instrumented calls across three predictions.
The76-residue trajectory has CA RMSD1.115Å, exceeding0.5Å;96-residue trajectory
0.223Å passes. No new backbone breaks. A distinct prototype retaining the
original BF16 product/sum/probability rounding boundaries is queued. It uses an
explicit rounded-arithmetic NumPy oracle and≤0.001 relative L2 both to that
oracle and to existing MLX before prediction; original trajectory gates remain.
This does not relax the FP32-attention candidate's gates. Symbolic dtype analysis
on tiny CPU arrays confirmed BF16 products/sums, then FP32 scale/bias.25 CPU
tests pass, including ties-to-even rounding against independent Torch conversion.

Protenix/Constraint matched-draw replays capture/replay401 identical Torch draws
per input but still fail structural gates. Constraint SUMO core RMSD10.689Å;
Protenix ubiquitin12.852Å. All confidence/error-matrix failures remain recorded.
Within-baseline smoke-versus-capture coordinates reproduce within0.00001Å,
saved in `baseline_capture_reproducibility.json`; capture instrumentation itself
does not explain the mismatch. No runtime promotion; input/intermediate-level
localization remains untested. Do not claim the difference is solely arithmetic
until all input and non-Torch random pathways are independently checked.

### Confirmation and endpoint refinement (22:43 UTC)
SUMO policyv3 explicitly excludes fixture positions1–20 before applying baseline
pLDDT≥80, so overconfident predictions of the mobile tail cannot contaminate the
core comparison. The20-residue exclusion is a conservative comparison mask, not
a universal domain boundary; primary support for an approximately20-residue tail:
https://pmc.ncbi.nlm.nih.gov/articles/PMC3660650/. Earlier v2 audits are archived.
29 CPU tests pass, including overconfident-tail exclusion, unsupported attention
shapes, replaced parameters and reused temporary-object identities.

The native RFD3 SDPA screen passed (CA RMSD0.105/0.187Å), but the fresh reversed
order confirmation measured18.879s existing versus19.914s SDPA:5.5% slower.
Its earlier apparent26% improvement was not confirmed. Keep existing attention.
The rounding-preserving Metal prototype matched its rounded oracle exactly in
its first case but differed from existing MLX by0.007605 relative L2, above0.001;
it stopped before prediction. No threshold was relaxed, and neither custom
kernel is promoted. The relation between graph dtype boundaries and actual
fused-kernel rounding remains an investigation, not a demonstrated cause.

NESSO baseline2.11 CCD cache passes:18.882→13.452s against earlier control.
The2.14 contemporaneous cache result also passes. AntiFold's both-shape-warmed
confirmation passes: eight outputs0.679566→0.617781s (9.1% reduction), much
smaller than its first-shape-compilation-sensitive screen. The headline figure
now uses the warmed mean equivalent two-input time for AntiFold.

OpenFold prototype failures are retained:2.6 MPS SDPA cannot safely accept the
unequal V width used in the first generic oracle, and its high-rank path aborted
inside MPSGraph in the second. The tested wrapper now requires equal Q/K/V
width and flattens independent leading dimensions into a supported4D batch.
Initializer coverage now follows owning Linear modules and verifies every final
parameter against the strict checkpoint. The second attempt completed three
predictions but failed final accounting because Python recycled identities of
discarded temporary modules; per-event weak references fix this without weakening
the live-module coverage guard. Final retries remain in progress.

### Final outcome
Completed the bounded screen:48 plans terminal (38 completed,8 failures retained,
2 cancelled before inference).60 unique completed blocks and162 audited output
units:51 warmups,7 profiled,104 measured/replay units. Completed output receipts
have zero audit errors. Installed Torch/MLX package versions remain unchanged.
29 CPU tests passed; no app source/default changes, commit or Swift build.

Final OpenFold initialization retry completed with4455 initializer events:
4401 live parameter checks,54 discarded temporary layers,740840544 elements
verified,3 strict checkpoint loads. Measured87.237→52.116s against the earlier
control. Ubiquitin CA RMSD0.000392Å; SUMO whole-chain diagnostic0.003320Å;
confidence/error matrices and geometry checks pass. SUMO core remains unavailable.
Final OpenFold SDPA wrapper completed20109 calls,87.237→84.680s against earlier
control; other gates pass, SUMO core unavailable. This2.9% difference is not an
established speed gain. No further runtime promotion or speculative retries.

The authoritative current conclusions are in
`Validation/output/apple_runtime_throughput_v2/DECISIONS.md`; the report includes
all contrary results and failed attempts, and both final SVG/PNG figures were
visually inspected. Padding gains apply only to total input lengths≤128 tokens,
so these monomer results must not be advertised as larger binder-complex gains.
Full-campaign, interface-ranking, larger-shape, combined-optimization, restart,
memory-soak and other-device validation remain untested as listed in FINAL_AUDIT.
