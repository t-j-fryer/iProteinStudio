---
entry: 0061
title: Test resident-request overhead optimizations
date: 2026-09-29
author: Codex
type: benchmark
status: completed
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.6.1
tags: [performance, predictors, openfold3, intellifold, boltz]
---

## Context
Follow up completed SUMO matrix (project0228/Validation0060). User requests deeper overhead research and measured optimizations at128-row MSA/reduced steps with five seeds. Preserve the old matrix, installed app/runtime packages and paused biotin.

## What was done
Predeclared experiment Validation/experiments/sumo_request_overhead_v1. Initial screen: OpenFold workers10 baseline,0,1,2,0 with continuous MPS residency; Boltz baseline and MPS residency; IntelliFold Flash/Full baseline and resident CCD cache. Each process loads once, runs one uncounted warmup42, seeds42-46, and separate cProfile diagnostic42. All requests128-row MSA,25 diffusion steps, native recycles unchanged,exact96 tokens. GPU work goes through immutable broker plan and shared lease. Hooks are process-local; no installed code edits. OpenFold0-worker feature preparation reproduces native worker0 RNG in a saved/restored CPU RNG context. Final cleanup restores patched methods and releases MPS model.

## Results
Completed; final measured results and limitations appear below. Actual multiprocessing spawn/import regression passes. Historical controls are preserved but fresh controls are used for causal comparisons. Individual diagnostic profiles excluded from timing summaries.

## Decision and rationale
Source/docs identify macOS spawn, per-request Lightning model.cpu teardown, and IntelliFold CCD unpickling. Profile these then investigate deterministic input reuse and bounded prefetch. Protenix/ESMFold have tiny measured non-inference overhead in prior matrix; prioritize the four models with material overhead. Do not change scientific settings or silently cache seed-dependent features. Five-seed structures/confidence/geometry and crystal-core comparisons required before claiming a usable speedup; practical changes may remain experimental pending campaign/resume/memory qualification.

## Reproduce
Run prepare.py with managed control Python, inspect saved plan, start via studioctl immutable digest. Frozen worker/config/hooks and per-arm logs/measurements under Validation/output/sumo_request_overhead_v1. Native versions/MSA SHA/host inherited from exact matrix frozen manifest.

## Limits and what was not tested
One target, one Mac. No app promotion, release, other-chip test or long campaign soak yet. Independent phase1 processes are serialized rather than randomized; warmup isolated. Potential full preparation caching and prefetch require follow-up profiling and output-equivalence controls.

## References
https://docs.pytorch.org/docs/stable/data.html (macOS spawn, worker persistence)
https://lightning.ai/docs/pytorch/LTS/_modules/pytorch_lightning/strategies/strategy.html (teardown); installed runtime source independently inspected.

## Next
Screen complete; production integration requires broader campaign and lifecycle qualification.

### Initial harness recovery and power management
First job-fa01e8bd48cc failed before model execution because broker-bound config moved into bound_configs while run.py incorrectly resolved worker.py beside that config. Corrected to resolve beside __file__, and actual subprocess regression with config in a different directory passes. Original attempt preserved. Retry plan-8329255a694c0375 / job-8329255a694c running under output/sumo_request_overhead_v1_retry01. Installed engines all system_detect state=ok. Per-user request, independent caffeinate PID55535 runs up to4h in addition to broker-scoped caffeinate; pmset confirms active system/display idle-sleep prevention. No permanent macOS power setting changed.

Protenix source comparison: core/ccd.py caches the CCD CIF and per-component info with lru_cache; RDKit dictionary is loaded once into module-global _ccd_rdkit_mols. ESMFold Studio Session retains builder and MLX models and calls model directly; no Lightning per-request lifecycle. These are structural precedents for the experimental cache/residency changes, not a claim of transferable speedup without measurement.

### Phase1 profiler and follow-up
OpenFold10-worker fresh baseline completed5 warm normal seeds: median16.8493s/request,3.0364s inference,13.7921s outside inference; core RMSD2.37079Å, no geometry violations. Separate cProfile diagnostic17.264s contains11.978s in poll/select waits, including input-worker wait and teardown; this is a diagnostic observation, not normal throughput. Initial1-worker pairs show core-coordinate differences below0.00001Å but little time improvement; no final conclusion until all five.

The process-local w0_keep hook initially failed in teardown after producing its first structure: Python closure captured a later reassignment of original. Corrected by binding each original callable as a function default. Failed attempt retained, no installed engine edit. Follow-up job-296e8e0e4869 is queued through shared GPU lock: corrected w0_keep plus OpenFold directory-style five-seed batch with0 versus2 workers (prefetch_factor1, separate warmup, CPU feature RNG isolated to match single-item controls), and IntelliFold Flash deterministic processed-input cache on top of CCD cache. Batch timing will be labelled amortized batch throughput, not five independent resident submissions. Prepared-input caching restricted to protein-only cached-MSA/no-template/no-constraint inputs; parsed artifacts copied, stochastic dataset features recomputed.

Evaluation will report exactness and practical numerical differences separately. Intended conservative screen: aligned core difference<=0.01Å, no new geometry defects, pTM difference<=0.0001, normalized pLDDT<=0.001, pair-error arrays<=0.01Å. This numerical screen was specified after inspecting the tiny1-worker coordinate differences; it is not a preregistered clinical/scientific guarantee. No promotion before broader lifecycle testing.

### Five-seed screen checkpoint
Fresh normal warm medians on the declared M4 Max: OpenFold10/1/2/0 workers16.8493/16.3057/16.4403/5.2380s. Zero-worker saves68.9%; maximum paired core-coordinate RMSD0.00000829Å; core CA-lDDT unchanged; no geometry violations. Separate baseline diagnostic partitions6.978s input wait,5.003s worker shutdown,0.691s model-to-device,0.666s trainer teardown. Diagnostic overhead excluded from normal medians.

Boltz baseline3.71024→continuous-MPS2.45376s (33.86% reduction), all5 paired full-atom coordinates and audited confidence values identical. Flash baseline6.39465→CCD-cache3.82736s (40.15% reduction), all5 paired coordinates/confidence arrays identical; no geometry violations. Separate Flash diagnostic CCD-load2.21445s baseline versus0.00000425s cached, total preprocessing2.54841→0.01407s (normal throughput measured separately). Full comparison remains running.

Profiler-directed deep follow-up plan-f3f5676161d74fd7/job-f3f5676161d7 queued after the first follow-up. OpenFold reference-feature construction still consumes about0.8s in the zero-worker diagnostic; test content-keyed, deep-copied CPU features under the same isolated native feature RNG, with seed/query metadata still created per request. Boltz repeated conformer selection/input parsing contributes about0.2s; test deterministic processed artifacts for the same protein/MSA on top of MPS residency. Both caches deliberately experimental, protein-only, no templates/constraints/ligands, no installed changes. Source inspired by Protenix cached component data and ESMFold retained builder/direct inference.

### Further profiling and controls
Profiler exposes an additional generic OpenFold preparation cost:196 torch.tensor calls in featurize_reference_conformers_of3 total0.585s, chiefly creating tensors from lists of RDKit Point3D objects. A process-local AST substitution changes only that named coordinate conversion to torch.from_numpy(np.asarray(coords,dtype=float32)); a CPU regression proves all native conformer feature tensors, including identical seeded reference-coordinate augmentation, remain exactly equal. Three actual CPU hook tests pass: teardown closure/restoration, cached-storage copy and sequence/MSA-content invalidation, and complete native coordinate-featurizer equivalence. No installed package edited. Five-seed job-ba3856f9ccba queued under output/sumo_request_overhead_v1_arrays.

IntelliFold Full first control showed slower model computation than its cached arm, separate from preprocessing. Added baseline_recheck five-seed control job-0d33975ddb9d/output/sumo_request_overhead_v1_confirmation to avoid attributing compute drift to the cache. No repeated benchmark merely to pick a favourable number; all initial/recheck results will remain reported.

### Final controlled follow-up
Full repeated control inference time drifted materially (about21s versus28–30s in prior arms), so a final within-session alternating CCD cache on/off comparison is declared before running it: seeds42–46 each tested both ways, order reversed on odd seeds, one warmup. OpenFold feature-cache receipts showed zero hits: query_name was incorrectly included in the content key. Final features_keyed variant removes only this output identifier; native feature creation does not use query_name, and native __getitem__ attaches query/seed metadata after features. CPU regression now changes request name and proves a hit, while changing sequence/MSA contents still invalidates. Original zero-hit arm is preserved and will be labelled as such.

## Final results and disposition
Completed this experimental screen, not a production promotion. Base commit00d299abf6f0b93cf1e4f0fff365e196edefb8ca; pre-existing dirty work preserved. Frozen source/runtime hashes are in each plan/config. Final plan143ed9996056f06c/job-143ed9996056 completed both arms. Failed initial harness runs remain preserved.

95 normal separate requests,35 warmup/diagnostic outputs and10 batch predictions audited: zero audit errors, zero geometry flags. All19 normal conditions have5 seeds; all paired conditions pass the numerical screen. Boltz/IntelliFold saved coordinates and compared confidence fields are exactly identical. OpenFold largest paired core difference across normal variants below0.000013Å, unchanged core CA-lDDT. Three actual CPU hook tests and one worker spawn/import regression pass. No forbidden MPS fallback messages found. Completed normal resident processes loaded once; all cleanup receipts show CPU model after the session.

Final normal medians from analysis/results.json:

|Engine|Variant|Request s|Model s|Outside s|
|---|---|---:|---:|---:|
|openfold3|baseline|16.84927|3.03640|13.79209|
|openfold3|w0_keep|4.05733|3.01995|1.07903|
|openfold3|w1|16.30572|3.01784|13.22954|
|openfold3|w2|16.44034|3.12943|13.31060|
|openfold3|w0|5.23796|3.02994|2.20086|
|boltz|baseline|3.71024|1.71070|2.00135|
|boltz|keep|2.45376|1.74131|0.71252|
|intellifold_flash|baseline|6.39465|3.45471|2.93994|
|intellifold_flash|ccd|3.82736|3.44571|0.38326|
|intellifold_full|baseline|33.17446|30.10566|3.14542|
|intellifold_full|ccd|28.89572|28.48345|0.40542|
|intellifold_flash|ccd_prepared|3.77884|3.40398|0.37295|
|openfold3|w0_keep_features|4.06889|2.99239|1.06754|
|boltz|keep_prepared|2.22243|1.73236|0.48489|
|openfold3|w0_keep_arrays|4.00069|2.98373|1.01151|
|intellifold_full|baseline_recheck|25.30012|22.25645|3.06872|
|openfold3|w0_keep_features_keyed|3.20422|2.97257|0.22092|
|intellifold_full|ccd_interleaved|29.50281|29.06311|0.45292|
|intellifold_full|baseline_interleaved|30.75631|27.52756|3.25708|

OpenFold0workers+MPS cuts request median75.9% versus10workercontrol; corrected identical-input cache adds21.0% reduction with6hits/1miss including warmup/diagnostic. Original cache attempt had0hits due request names in key and is retained. BoltzMPS cuts33.9%, parsed identical input adds9.4%. FlashCCDcache cuts40.1%; parsed-input cache adds little.

Full control/model times drifted materially between runs. Final alternating same-session pairs show median paired request saving1.901s but2/5pairs slower; outside-model saving is consistent: median2.804s, range2.720–2.921s. Do not promote the initial overall percentage as a reliable causal effect. All Full outputs remain exactly equal.

Generic OpenFold NumPy coordinate conversion did not establish material benefit; profiler shows conversion cost moving between libraries. Directory prefetch: one5-seed batch0workers20.44465s total/5=4.08893s,2workers32.51402s/5=6.50280s. More worker processes lose for this short workload. Larger queues/persistent producer threads untested.

Protenix/ESMFold provide useful patterns: retain chemistry dictionaries/builders and models, key deterministic caches by scientific input, preserve stochastic preparation. Repeated-seed feature reuse is not automatically reusable for changing binder sequences.

Deliverables under Validation/output/sumo_request_overhead_v1_retry01: REPORT.md,OVERVIEW.svg,BATCH_THROUGHPUT.svg and analysis/{results,batch_results,hashes}.json. Report preserves all controls, load/warmup costs and cache receipts. No installed packages/app defaults/source promoted, no commit/release or Swift build for this Python validation task. Biotin remains paused.

Not tested: other proteins/Macs, variable-length campaigns, complexes/templates/ligands, long memory soak, cancellation/restart with hooks. Caches need bounded storage and broader scientific keys before production integration. Protenix/ESMFold not rerun because prior matrix showed little relevant overhead. CPU-thread sweeps not added where process startup/data loading/device transfers dominated. Thermal telemetry was unavailable; no cause claimed for inference-time variation.

Final overview PNG visually checked: labels and panels legible. Broker final job confirmed completed; released only our independently started caffeinate PID55535 after verifying its exact command. Broker-scoped assertions ended with their jobs. Idle sleep was prevented throughout testing; no permanent power settings changed.
