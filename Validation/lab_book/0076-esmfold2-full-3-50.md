# 0076 — Four-target ESMFold2 Full 3/50 validation

2026-10-01, in progress. [Project0251](../../lab_book/0251-queue-esmfold2-full-3-50.md).
Apple M4 Max64GB. Five seeds42–46 per target plus one excluded warmup; Smt3,
T4 lysozyme, MBP and citrate-synthase dimer. MSA128,3loops,50requested steps;
same precision, assets, exact inputs and profiling as the historical Full20/100
controls. This is a compute-profile comparison, not isolated software acceleration.

Executable experiment: `experiments/esmfold2_full_3_50_v1`. Immutable generated
manifest records current revision, upstream runtime/checkpoint fingerprints,
cached MSA hashes and all20 original control receipts. Raw outputs stay immutable;
output hashes, finite coordinates/sequence cardinality, crystal alignment and
geometry use the original harness. Warmup/model identity and MSA shape are audited
before paired comparison. Two CPU protocol tests and frozen preflight pass; no
new GPU measurements yet. OOM is recorded, not hidden by lowering settings.

Queue: current Hunter GPU acceptance tests → this block → paused Protenix v2
five-seed block → binder screen. Shared broker lock used for every prediction.
No production defaults promoted. GPU performance, full-campaign quality and
production restart/cancellation/memory qualification remain pending.

Launch update: latest GPU acceptance receipts all completed, including RFD3 retry and Boltz Full resume check. The watcher submitted plan `plan-86082086db222eb5` as `job-86082086db22` at20:06:42UTC. Broker reports running; first Smt3 block entered. No acceptance work was cancelled.

First-block verification: Smt3 warmup and all five measured seeds finished; paired receipt, exact MSA128 and same-resident audit passed. T4 lysozyme has started. Partial analysis is generated and will refresh at campaign completion.

## Completed benchmark review (2026-10-01)

All20 measured predictions and four warmups completed; all20 measured outputs passed the saved geometry audit, exact MSA128, output-hash and same-resident checks. No OOM. Measured on this Apple M4 Max64GB; historical controls from prediction_scale_v1.

| Target | Median request20/100 →3/50 (s) | Median crystal CA RMSD20/100 →3/50 (Å) |
|---|---:|---:|
| smt3 | 5.819 → 1.466 | 2.360 → 2.295 |
| t4_lysozyme | 18.422 → 3.370 | 1.512 → 1.221 |
| mbp | 102.679 → 33.429 | 1.381 → 3.008 |
| citrate_synthase | 724.468 → 185.878 | 2.304 → 1.572 |

MBP domains remain essentially unchanged: median N-domain RMSD0.457→0.455Å and C-domain0.567→0.563Å. The global difference concerns domain arrangement. It is not a uniform deterioration: three of five paired seeds improved, two worsened. Five seeds do not establish a systematic quality loss or equivalence.

Peak recorded process-tree physical footprint in the new measured outputs was20.14/20.72/22.49/45.80GiB (Smt3/T4/MBP/dimer), broadly unchanged from20.25/20.72/22.29/45.40GiB. These are sampled process-accounting measurements, not total system RAM.

Timing caveat: the other chat started production Swift compilation around20:27UTC while dimer seed45 was running. Possible CPU/host contention affects interpretation of the final dimer seeds. These are instrumented historical-control comparisons, not isolated or randomized idle-host runs.

Queue: ESM job completed20:30:31UTC. The other chat deliberately SIGSTOP-held watcher68597 for final acceptance/app staging; Protenix has not resumed. Respect that hold; the releasing chat is to SIGCONT the same watcher, which retains Protenix→binder ordering.

App defaults remain unchanged pending qualification and review of MBP conformational variability.
