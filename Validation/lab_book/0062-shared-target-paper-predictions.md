---
entry: 0062
title: Optimize shared-target prediction and screen paper binders
date: 2026-09-30
author: Codex
type: benchmark
status: in-progress
machine: Apple M4 Max, 40-core GPU, 64 GB, macOS 26.6.1
tags: [performance, prediction, msa, paper]
---

## Context
User requests optimizations for many different binders against the same target, covering preparation and compute, followed by the supplied674-design table on all8 previously benchmarked prediction engines except IntelliFoldFull. SUMO must be96aa benchmarksequence; binders explicit noMSA; targetMSA cap128/reducedsteps, exceptESMFast noMSA/full50steps. One seed per design assumed pending optional question;5 different binders/seeds42–46 in paired optimization screen.

## What was done
Frozen originalCSV and extracted targetMSAs from completedAF3 *_data.json files under user-supplied folder.7 distinct effective target sequences. SUMO uses known96aa/128rowMSA; other targets first128 supplied rows, or all available. ALFA12/13 andMyc11 have2 duplicatequery records and nohomologs; explicitly labelled query_only. No remote search necessary. Main binder column equalsdesigned;33 nonempty assayed sequence differences are preserved in metadata but notsubstituted. One Myc-labelled row is TrxA108 by sequence/designID; retain sequence andflag label inconsistency.

## Hypotheses and declared comparisons
Five varied SUMO binders spanning tablelengths, same counterpart seed in eacharm, one warmup and separate cProfile diagnostic. Existing zeroOpenFoldworkers/MPSresidency/CCDcache first verified oncomplexes. Bounded deepcopied targetMSA parsing cache preserves native stochastic featurization. ESMFold2 chainwise ESMC targetembedding cache exploits native chain-isolated attention; rotary/rounding changes must pass paired outputgate, not assumedexact. CPU overhead candidate inference_mode onProtenix/Flash; compute candidate PYTORCH_MPS_PREFER_METAL=1 (no fastmath), documentedPyTorch backendchoice. Fullcomplex interactions/recycling mustalwaysrecompute; no diffusion/recycle/precision reductions beyond requestedprofile. No globalapp changes. AllGPU work immutablebrokerplan/sharedlock/caffeinate. Initial22arms listedinprepare.py; stage timings synchronized allarms so instrumentationconsistent. Library code is pinned by inherited runtime manifests. Model weights are external assets; direct checkpoint/data fingerprints are added for the full campaign.

## Results
Optimization qualification completed:187 audited normal predictions; detailed measured results and rejected candidates below. Mac keptawake by independent12h caffeinate plus jobscopedassertions. Prior biotin remainspaused.

## Numerical gates
Predeclared completecomplex backboneRMSD<=0.1A and binderRMSDaftertargetcorealignment<=0.2A; confidence scalarmaxdelta<=0.01, meanPAEdelta<=0.1A, noadditional severegeometrydefects. Report exactarrays separately and oldstrictermonomercriteria. Never interpret similaritytobaselineasexperimentalaccuracy proof.

## Reproduce
Validation/experiments/paper_binder_matrix_v1/{inventory,prepare,run,worker,engines,reuse}.py. Outputs Validation/output/paper_binder_matrix_v1. Freeze prepare.py under managed controlPython, review plan, studioctl start withdigest. Benchmarkqualifies candidates before fullcampaign. Rawoutputsimmutable, complete.json hashes perunit; restartonlyverifiedunits. Sourcecommit 00d299abf6f0b93cf1e4f0fff365e196edefb8ca pluspre-existingdirtywork, frozenactualcodehashes.

## Limits and what was not tested
Otherhardware andlongmemorysoak pending; no releaseddefaults. Syntheticpeptidetags have no genuineMSA. Widerprotein/campaignstabilitychecked viarequested674rows only after smoke/outputaudits. No ligand/templateoptimizations.

## References
https://docs.pytorch.org/docs/2.14/mps_environment_variables.html
https://docs.pytorch.org/docs/2.14/generated/torch.autograd.grad_mode.inference_mode.html
InstalledESMFold2MLXcompute_lm_hidden_states explicitly isolates attention bychain sequenceID; nativecode governs tests.

## Next
Run/audit pairedscreen; select only validatedwins, complete newtargetsmokes, submit resumable fullcampaign, report timings/quality andunaltered inputmapping.

Initial benchmark plan21ac7856ec13f5a7 / job-21ac7856ec13 started after review. NativeBoltzparser CPUtest passed exactarrays, independentcache storage, maxseqparameter invalidation andrestore. FirstCPUtest importing full boltz.main lacked writableNumba cache and failedbeforetest; rerun scoped to parser withtmpNumba pathpassed. Worker sets privateNumba directory beforeimports. Independentcaffeinate PID66226 verifiedactive. SelectedSUMObinderlengths64,98,117,135,150; pairedseeds42–46.

Initialbenchmark cancelledafter firstBoltzstructure succeeded but newworker audit importedBiotite absentinBoltzruntime. No enginefailure; scientificoutputpreserved. Replaced audit with existingStudio dependency-free cif_atom_rows/read_cif, plus NumPyfiniteconfidencechecks. Actually auditedsavedtwochaincomplex inBoltzPython successfully (4hashedfiles), includingsequence/backbone/confidence. Newimmutableattemptbenchmark_retry01 prepared; no rawoverwrite.

Retry plan-e389c7aec1447246/job-e389c7aec144 running with dependency-free audit. FirstBoltzbaseline completed all7 outputs. Futurecampaigninstrumentation further separates nativewriter/JSONserialization from otheroutside-model time; frozenbenchmark unchanged. Resume coordinator now verifies allcompletedarm hashes and discovers prior completedretryunits beforedoingnewwork.

Profiler-directed OpenFold improvement beyond previous failedarrayconversion: bypass RDKitPoint3D Pythonobjects entirely using Conformer.GetPositions() and then identicalcrop/float32conversion/nativeaugmentation. CPU functionaltest100glycineresidues,3timedrepetitions percase: fullatom median0.601440→0.009093s; cropped0.453633→0.010948s. All nativefeaturetensors and permutationdicts exactlyequal withmatchedrandomseed. This is a CPUmicrobenchmark, not prediction throughput. Predeclare new positions phase withfresh residentcontrol andpositionscandidate,5variedSUMObinders/seeds42–46. Same scientificsettings/gates; noMCSPUdefaults modified.

Follow-up positions plan7de025e3a4425178/job-7de025e3a442 queued behind benchmark. OpenFoldtargetparserinspection shows native inference uses core.data.io.sequence.msa registry, not legacyparsers; frozen initialreuse arm hookslegacyparser and therefore is not a meaningfulcachehit test. Corrected sourcehook testedCPU onactual128rowSUMO A3M:5uncached median0.001919917s;5cached median0.000064167s (5hits/1miss). At~2ms/request this is immaterial; do not promote thiscache on an end-to-end speed claim. Leave frozenarmuntouched and reporthitcount. Positionsprototype attacks the muchlargerconformerconversioncost.

### Protenix invariant diffusion cache follow-up
Native `enable_diffusion_shared_vars_cache` computes conditioning once within each prediction, without reusing joint features across binders. Prior monomer screen in `apple_runtime_throughput_v2/REPORT.md` saw only 2–3.5% earlier-control differences, insufficient to promote. Retesting v2 and Constraint with fresh controls on five paired SUMO complexes. Plan `6e8ead56abe3e566` queued behind main/positions screens. Pair/atom-conditioning call counters record CPU dispatch only; outer model and diffusion timers synchronize GPU. An earlier prepared plan `2f3b6a41b30ba9fe` was never started: its per-call fences would bias the comparison toward fewer calls. Both immutable plans retained. No weights, precision, recycle or denoising settings changed.

Main OpenFold MSA-cache arm failed at import because the frozen legacy parser module is absent, rather than merely recording zero hits. Source fix/CPU measurement above still applies; no end-to-end reuse claim. ESMFast baseline produced and independently checkpointed all seven outputs, then failed in cleanup reporting because MLX `parameters()` returns a dict rather than a Torch iterator. Corrected source cleanup type dispatch for future runs; immutable raw predictions remain valid and analyzable. Frozen main ESM arms may show the same final-report failure, which is distinct from prediction failure.

### Chain-isolated language-model embedding experiment
ESMFast's first chainwise cache finishes all five normal predictions, but fails the predeclared numerical gate on three. Worst complete-backbone RMSD0.14865Å and ipSAE(min) delta0.02954; smaller cases pass. Gate is not relaxed after seeing results. Native code isolates attention by chain but uses global rotary positions; splitting chains resets target positions and can change low-precision rounding. Follow-up `esm_offset`, plan b4aee41f81d352a6, preserves native positional offsets and keys cached target states by both sequence and offset. Bounded512MB cache. Fresh five-binder controls for Fast/Full; same scientific settings. Source cleanup bug fixed and a dictionary-parameter MLX regression test passes. Prediction export tested on actual Boltz, Flash, OpenFold and ESMFast outputs, including native/derived ipSAE checks and SUMO crystal-core fit.

All674 binder/target sequence pairs are unique; there is no duplicate-input work to eliminate in the paper table. Boltz residency is numerically exact and reduces measured outside-model time, but whole-request timing varied enough that the independent request medians and paired differences disagree. Added a reversed-order five-binder confirmation (resident first, native second) before choosing it for674 submissions. No confidence or performance threshold changes.

### Duplicate template computation (Protenix v2)
Source inspection shows four padded template rows are passed through the template pairformer even without templates. Their learned contribution is not zero: skipping the template module would change the model. Added process-local reuse only when all five native input-feature rows match exactly. Cache resets for every recycle; the native summation, normalization, activation and output projection remain untouched. No feature/result reuse across complexes or recycles.
Actual upstream CPU TemplateEmbedder tests with randomized nonzero weights pass bit-exact output equality for four identical rows and for mixed identical/distinct rows. Changing z between calls verifies cache invalidation; real single-template calls fall8→2 or8→4 across two calls respectively. GPU/full-model equivalence and throughput still pending. Constraint and Mini have no template blocks and are excluded.
Consolidated follow-ups into compute_cache: v2 native/diffcache/templates/templates+diffcache and Constraint native/diffcache, each five paired binders plus warmup/profile. Cancelled still-queued job6e8ead56abe3 before any prediction and left standalone templates plan1d2be1d56abe6496 unstarted; avoids repeating a seven-output v2 control. All plans and cancellation evidence retained. Boltz reversed-order confirmation is job653cad00e76f.

Full-campaign harness now separates per-process session receipts (load/cache/cleanup) so a restart preserves earlier metadata. OpenFold retry/warmup query names include the unique attempt directory; this prevents native query outputs from overwriting an earlier attempt. Boltz profiling now targets the actual inferencev2 dataset; the initial screen's missing featurization timer is not reported as zero. ESM keyword-expanded model inputs are captured for MSA shape auditing; all72 previously captured native input shapes passed target/binder-length and real-MSA-depth checks.
The complete joined-report program was executed on a real Boltz output in an isolated fixture:1/1 audited with0errors. A deliberately altered local hash receipt was rejected (exit1,0accepted); original raw outputs unchanged. Receipt saved under output/tests/report_test.json. Actual Protenix v2 export also passes, including ipSAE agreement and native0–100 pLDDT normalization.

### Completed first screen (2026-09-30 05:25 UTC)
105/110 declared normal outputs audited with0integrity errors. The five missing outputs are the invalid OpenFold parser-hook arm. All eight native model controls completed. ESM predictions completed but their old cleanup-receipt code raised after saving/auditing; the broker job is therefore failed, not misrepresented as clean success. Fixed source is used for follow-ups/full campaign.

|Engine|Variant|Request median s|Outside-model median s|Median paired saving s|Output gate|
|---|---|---:|---:|---:|---|
|boltz|baseline|12.177|2.613|—|None|
|boltz|resident|12.761|1.271|0.747|True|
|boltz|reuse|12.813|1.264|-0.398|True|
|boltz|metal|13.432|1.262|-0.640|True|
|intellifold_flash|baseline|14.811|3.124|—|None|
|intellifold_flash|resident|13.123|0.550|1.688|True|
|intellifold_flash|inference|13.637|0.541|1.175|True|
|intellifold_flash|metal|13.449|0.540|1.363|True|
|openfold3|baseline|48.495|27.874|—|None|
|openfold3|resident|41.648|4.039|10.781|True|
|esmfold2_fast|baseline|10.442|0.066|—|None|
|esmfold2_fast|chain|3.825|0.072|6.450|False|
|esmfold2_full|baseline|31.133|0.066|—|None|
|esmfold2_full|chain|33.312|0.073|-1.806|False|
|protenix_v2|baseline|52.446|0.255|—|None|
|protenix_v2|inference|52.836|0.259|-0.031|True|
|protenix_v2|metal|52.247|0.256|0.199|True|
|protenix_mini|baseline|3.197|0.240|—|None|
|protenix_mini|inference|3.129|0.238|0.068|True|
|protenix_constraint|baseline|21.511|0.235|—|None|
|protenix_constraint|inference|21.282|0.237|0.229|True|

Raw/derived details: output/paper_binder_matrix_v1/benchmark_retry01/{REPORT.md,analysis/results.json,OVERVIEW.svg}. Baseline-to-candidate tests pair the same five binder sequences/seeds; fixed arm order and transient GPU/compilation variation limit small speed claims. ESM chain cache fails numerical limits and is not selected. Flash CCD cache is exact and useful. Protenix inference-mode/Metal differences are small and do not justify promotion from this screen alone. OpenFold residency passes; direct coordinate-array and compute-cache follow-ups pending. No app defaults changed.

Full-campaign supervisor test passed with a simulated worker exit9 followed by success: one bounded retry, two preserved logs, live progress forwarding, and a completed-arm resume that did not invoke the worker again. Scientific prediction execution remains through the broker GPU lease.

Full-campaign preparation now fingerprints external checkpoint files and selected CCD/config assets without copying weights. Each resident process verifies those content hashes before loading and records verification time separately. Component runtime manifests deliberately exclude model weights, so they alone are not checkpoint fingerprints. Existing benchmark checkpoints were loaded from their recorded version-named paths; direct weight fingerprints will be captured after the GPU screens to avoid concurrent hashing I/O during timing. Asset guard CPU test passes and rejects a same-size content mutation.

### Selective trunk precision probe (prospective)
The dominant remaining cost is the Protenix v2 trunk. Earlier Boltz diffusion-only BF16 in Lab0168 was slower and failed fidelity; that is not evidence about the larger Protenix trunk. Declare a short paired probe on the64aa binder/SUMO96 seed42: one warmup and one measured prediction each, nativeFP32 versus MPS BF16 autocast only within get_pairformer_output. Stored weights, diffusion and confidence stayFP32; returned trunk tensors explicitlycast backFP32. Record an actual pairformer linear's output dtype. Same numerical thresholds. Expand to five binders only if this initial probe is both faster and within gate; no promotion from onepair. Plan d1de5a71e01dc251/job-d1de5a71e01d queued.
Independent export now tested on actual seed42 complexes from all eight engines: exact chain sequences, finite native confidences, conservative ipSAE agreement whereavailable, and SUMO core alignment. OpenFold ipSAE explicitlyunavailable. Receipt output/tests/eight_engine_export.json.

### Completed compute-cache comparison and recovery checks
The five-pair Protenix v2 follow-up found no whole-request improvement: baseline median50.567s; diffusion cache51.644s; duplicate-template cache51.229s; combined50.663s. All pass the unchanged numerical gate; none is selected for speed. Constraint native diffusion caching improved every paired request (0.281–0.572s), median paired saving0.517s; request medians21.651→21.080s, synchronized diffusion medians1.590→1.415s. All five pass, maximum backbone RMSD about0.000060Å. These are five different binder/seed pairs on the recorded M4Max, not a broad hardware claim.

Reproducible CPU-only control tests now live in experiments/paper_binder_matrix_v1/test_control.py. Both pass: bounded retry with distinct retained logs, forwarding live progress, verified completed-arm resume without re-execution, rejection of a tampered completed receipt; and asset hashing rejecting a same-size content mutation. No GPU work is performed by these control tests.

Timing caveat discovered during the independent OpenFold follow-up: the unchanged resident control itself became much faster between sessions (117aa binder request41.648→13.123s; model37.609→10.776s). Same runtime, scientific settings, and [1,129,213,32] native merged-MSA shape; across all five controls the largest backbone difference is0.000043Å and scalar confidence changes are negligible. The supplied target cap128 becomes129 merged OpenFold rows through its native query handling. We do not attribute the cross-session speed change to the coordinate-array patch. Only its within-phase paired contrast is used. GPU/runtime warm-state or system load may contribute; their individual effects were not isolated. Receipt tests/openfold_cross_session.json.

### OpenFold coordinate-array qualification
The positions follow-up completed cleanly,10/10 normal predictions audited with no errors. Resident control vs direct RDKit coordinate arrays: request medians13.123→12.478s; outside-model medians2.347→0.991s; paired request saving0.645s. All5 numerical gates pass. This includes zero loader workers and MPS residency in both arms; it is the additional coordinate-conversion saving, not a comparison against the original10-worker control. Native feature CPU test preserved tensors exactly; final GPU outputs differ only at very small rounding levels. Follow-up plan7de025e3a4425178/job7de025e3a442 completed.

### Trunk BF16 probe rejected without expansion
Plan d1de5a71e01dc251 completed cleanly. On the one declared64aa binder/seed42 pair, Protenix v2 trunk-only BF16 reduced measured request23.269→19.491s (16.2%). Backbone RMSD0.075Å and ipSAE delta0.00551 were within limits, but maximum normalized atom pLDDT change0.020 exceeded the fixed0.010 threshold. No extra geometry flags. The output gate fails; do not expand to five pairs or use this profile in the paper campaign. FP32 remains selected. This single pair does not establish a general precision/speed tradeoff.

Full-campaign external asset coverage expanded to include the21 canonical Boltz molecule files actually loaded by its protein preprocessing, in addition to the confidence checkpoint. All22 paths exist. No ligand affinity checkpoint is used in this protein-complex campaign.

### Final speed and embedding-cache comparisons
Boltz reversed-order confirmation (resident before baseline) completed cleanly,10/10 audited: baseline request14.394s versus resident13.622s, median paired saving0.773s, outside-model2.528→1.237s. Saved coordinates/confidences exactly equal for all5. Both original and reversed-order screens support keeping Boltz onMPS between requests.

The positional-offset-aware ESM cache completed all20 normal outputs and cleanup successfully. Fast baseline3.517s vs offset3.557s; only2/5 output gates pass. Full27.386→34.562s, paired saving−5.324s; all5 output gates fail. Neither is used. Splitting ESMC into per-chain calls changes BF16 numerical results despite preserving rotary offsets, and variable binder lengths also change the target's native position offset, limiting reuse. No claim of a validated embedding-cache speedup.

### Additional memory qualification (prospective)
Actual ESM driver allocations grew across the five distinct lengths: Fast18.33→35.90GiB; Full18.69→39.73GiB. The longest paper complex is371residues, versus246in the optimization panel. Native MLX defaults its free-buffer cache limit to its memory limit, so qualify a process-local4GiB free-cache cap before the long campaign. This preserves active model weights and arithmetic. Plan47c590dd1529e25c/job47c590dd1529 uses the same five binder/seed pairs, no cProfile replay. The immediately preceding esm_offset baseline is reused only for numerical equivalence; cross-session request differences are not treated as a speed comparison. Record active/cache/peak/driver allocation for every output. Full-campaign first-target smokes now use the longest binder for each target to exercise maximal lengths before the bulk.
Documentation: https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.set_cache_limit.html ; exact installed API docstring also read. No system-wide memory/wired limits or shared folders changed.

### Memory qualification and reviewed selection
The ESM4GiB free-cache qualification completed cleanly: all10 normal outputs audited and exactly equal to the preceding native controls. Fast driver allocations stay16.55–16.58GiB (active12.53GiB, free cacheabout4.0GiB); Full16.68–16.74GiB (active12.71GiB, free cacheabout4.0GiB). Native controls had grown to35.90/39.73GiB respectively. The allocator can momentarily exceed its target by an allocation block. No active weights or numerical operations changed. Request medians3.116/27.094s are recorded, but this cross-session comparison is used for memory/equality qualification rather than a causal speed claim.

Reviewed selection.json now records all8 choices and hashes of seven analysis result sets:187 audited normal qualification predictions total. Selected Boltz residency; Flash CCD cache; OpenFold0workers+residency+coordinate arrays; Constraint native diffusion cache; Protenix v2/Mini native paths; ESM native compute with bounded free allocator cache. Failed embedding/precision candidates are excluded. The full674×8=5392 campaign uses seed42, one prediction per design/engine, and starts each engine with the longest complex for each target. All674 binder/effective target sequences contain standard amino acids only. Full campaign preparation fingerprints external assets and freezes code before launch. No app defaults promoted; long-cohort soak and other hardware remain untested at this point.

### Full paper campaign launched
Reviewed immutable plan8b090b4b2f4e8957, SHA2568b090b4b2f4e89572b626a90447599c80b470229efb166b59f94923a4ae9421f; broker jobjob-8b090b4b2f4e submitted2026-09-30T06:25:13Z and running06:25:47Z. All5392 requested normal predictions are scheduled serially in eight resident engine sessions, with atomic per-unit receipts, one bounded worker retry, and independent exports after each engine. The code/runtime bindings, inputMSAs, selected variants and external checkpoint/data fingerprints are frozen under output/paper_binder_matrix_v1/campaign/frozen. Preflight took46.281s including32.110s brokerpreparation; no weights copied. The first engine is Boltz. At launch, the complete674-design cohort has NOT yet finished and the other engines' long-cohort behavior remains untested. Job-scoped caffeinatePID95636 confirmed active without a fixed timeout, in addition to the existing12h assertion. Prior biotin remains paused.

### Initial paper output audit
At 2026-09-30T06:29:26.067984+00:00, 13/5392 paper predictions independently audited with zero errors. Boltz completed the longest-binder smoke for all7 effective targets, including371residues, and continued into the main SUMO group. Export confirms requested25steps/3recycles and96aa SUMO. Full cohort and later engine cohorts remain running/pending; they are not reported complete. Initial joined prediction/stage/startup tables and coverage audit are under campaign/analysis; campaign/REPORT.md refreshes after each engine. Temporary12h caffeinatePID66226 was released after confirming the campaign's own lifetime-bound assertionPID95636. No permanent power settings changed.
