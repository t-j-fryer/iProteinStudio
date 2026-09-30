---
entry: 0060
title: Exact-token prediction and SUMO benchmark continuation
date: 2026-09-29
author: Codex
status: in-progress
machine: Apple M4 Max, 64GB, macOS26.6.1
---

## Context
User explicitly requests exact token sizes in all predictors, app Predict and MCP, stops current padded IntelliFold tests and repeats affected models.

## Work
Cancelled broker job-de244a02815c; completed original outputs retained. Shared IntelliFold policy now uses the upstream single bucket1, whose native overflow path returns actual token count. Both CLI and resident integrations consume this policy. Explicit older bucket requests remain reproducible. Boltz measured96 token inputs; OpenFold uses get_token_count; Protenix features are built from actual token arrays; ESM prepare_input uses len(tokens). Internal atom attention/block padding is not optional token bucketing. No packages or weights patched.

## Validation plan
New immutable experiment sumo_model_matrix_exact_v1: repeat Full/Flash matrices; continue OpenFold and three Protenix variants. Reuse unchanged Boltz and ESM raw outputs by explicit path. Full96 runs first. Same seeds, recycles, MSA inputs and diffusion budgets; record actual token dimensions and align crystalcore21–96. Test standalone CLI and resident path. Preserve paused biotin.

## Results
Pending live model qualification. Three shared-policy unit tests pass; extracted installed upstream calculate_bucket_size returns exact lengths for1,2,95,96,97,128,129,256,513,5121. No speed claims yet.

## Limits
One target; other chips and fresh install untested. Long-term memory soak and varied-size compile-cache behavior not yet qualified. No GitHub release published in this entry yet.

## Native acceptance and deployment checkpoint

Broker qualification job-bd09ff2380eb completed: both Full and Flash native CLI on96-token SUMO,97-token SUMO+G and103-token two-chain input. Native exact-size logs confirm all three lengths, six output/sequence-length/backbone/finite-confidence audits pass, native geometry violations0/errors0. This is functional acceptance, not a timing comparison: app compilation overlapped these smoke runs. Full/Flash native CLI preserve scientific defaults and use the new policy automatically, without explicit bucket flags.

App0.2.16/build62 built, codesign verified, relaunched at build/iProteinStudio.app. Installed scripts/intellifold_padding.py, nanohunter_run.sh and PIPELINE_VERSION hashes equal source, covering new Predict/MCP/Protein Hunter jobs. Existing snapshots retain their policies. MCP schema version35 unchanged. Swift default release build failed to resolve pinned Sparkle under the new toolchain build system; explicit established native SwiftPM build system fixed packaging. Standard swift build passed; native release build passed. First relaunch raced the previous app exit (-609); subsequent open succeeded.

Tests:3 padding-policy tests,4 prediction-safety tests,14 resident-resume tests (2 dependency-conditioned skips), iterative CLI contract including auto exact sizing and retained explicit legacy buckets, and packaged resource contract passed. Original padded benchmark remains cancelled. Replacement job-79f4ded1977b is launched;180 new normal predictions plus36 diagnostics, with70 normal/14 diagnostic unchanged outputs referenced from the original matrix. Biotin remains paused. No GitHub publication in this task yet.

## First paired resident result

Full seed42, SUMO no-MSA,10 recycles/200 diffusion steps, measured actual input [1,1,96,32]. Padded first request251.273491s versus exact first request30.720599s; model248.03s versus27.238156s. This is one paired first-call observation, not a warmed repeated summary. Core RMSD to3QHT2.349928706Å versus2.349929021Å; old/new core CA RMSD0.000013875Å, whole-chain CA RMSD0.000021423Å; exact output geometry errors0/violations0. Evidence: sumo_model_matrix_exact_v1/first_full_pair.json and immutable measurements. The matrix continues with5 seeds per condition.

## Five-seed no-MSA Full checkpoint

All five normal seeds42–46 and the diagnostic replay completed in the exact-sized resident worker. Paired warm request medians (4 warm pairs, first request excluded):253.791067s padded versus30.706320s exact. Across all5 paired seeds, maximum old/new core CA RMSD0.000013875Å. Evidence: analysis/padding_contrasts.json. This is the no-MSA/200-step cell only; MSA/reduced-step cells and Flash matrix are still running/queued. Controls were collected earlier, not interleaved contemporaneously. New code-snapshot capture includes all scripts, so new MCP plans see the new padding policy while existing immutable plans remain reproducible.

## OpenFold benchmark harness repair

OpenFold's first exact-matrix attempt failed before inference. Spawned DataLoader children re-executed the benchmark worker's top-level setup, attempted to recreate its existing output directory and raised FileExistsError. This is a benchmark entry-point bug, not a model or app-prediction failure. Added the standard main guard to the editable experiment worker; an actual multiprocessing spawn/import regression passes without model execution or filesystem mutation. Original frozen worker/logs remain unchanged. Preparing an OpenFold-only retry with identical scientific settings under a new immutable broker plan, queued behind the remaining Protenix v2 block. Production app/source is unaffected by this harness-only fix.

OpenFold retry plan-23f59a2013ccc5e5 (authoritative full ID/digest in retries/openfold3_01/plan.json), job-23f59a2013cc queued through the shared GPU lock. A CPU-only report watcher follows this retry and merges completed outputs into the exact-token matrix report.

## Progress/metrics checkpoint and OpenFold recovery

220 primary predictions/44 diagnostics completed across eight models. OpenFold retry01 initially failed because broker initialization created normalized output/openfold3_retry01/studio_job.json before the worker's strict exclusive mkdir. Retry02 uses the campaign parent as broker output and a separate prediction child directory, preserving strict no-overwrite protection. Broker job-d50af7aa9e4f is running. Five OpenFold no-MSA/200-step predictions independently audited; total225/250 primary predictions,44/50 diagnostics. OpenFold first-cell warm request median27.7997s, core RMSD median26.1571Å, core CA-lDDT0.0921, mean reported pLDDT median35.2886; geometry flagged5/5. These are poor scientific outputs, not a launch failure; MSA arms remain pending. The analysis confidence-file filter was corrected to exclude the full_data schema specifically, rather than accidentally excluding legitimate files whose query name contains full. Actual confidence/coordinate audits now pass for all225 outputs.

Compact results in PROGRESS_SUMMARY.md: at128 MSA, native→reduced request seconds/RMSDÅ: Boltz7.06→3.80/2.00→2.26; Flash9.40→6.27/2.34→2.32; Full37.81→30.35/2.29→2.30; Protenixv216.62→10.58/2.15→2.15; Constraint12.15→3.94/2.26→2.27; Mini0.90→0.67/2.30→2.12; ESMFull7.72→6.90/2.36→2.38. Fast sequence-only0.96→1.10/2.24→58.50. Mini1-step and ESM reduced geometry findings must accompany RMSD; no reduction promoted. Full padding gives253.79→30.71s no-MSA/200-step warm medians; Flash128→96 tokens saves8–16% of request time across all six cells with maximum core-coordinate difference<0.000046Å. No broad single-target accuracy claims.

## OpenFold MSA parser diagnosis and retry03 (2026-09-29 local)

Retry02 job-d50af7aa9e4f completed10 primary no-MSA predictions and2 diagnostic replays, then failed on128-full-42 before model inference. OpenFold parse_msas_direct filters raw alignment basenames against configured database slots: direct128.a3m/full.a3m paths yield an empty dictionary and parse_msas then raises IndexError. The benchmark bypassed Studio's existing openfold_query_json.py filename adapter; this finding does not demonstrate an app/MCP MSA-path bug.

Changed only the editable benchmark to invoke a frozen copy of the production query builder, preserving alignment bytes in its recognised colabfold_main.a3m slot. Added runtime checks for96 token columns and more than one MSA row on MSA-enabled requests. CPU-only native parser regression reproduces the original empty parses and verifies128x96 and8060x96 rows, query identity and unchanged source SHA256 checksums. Evidence: output/sumo_model_matrix_exact_v1/openfold_msa_parser_check.json. The actual spawn/import regression passes. No scientific settings, original frozen scripts or prior raw outputs changed.

Retry03 plan-65ca8a4f593a60c7 / job-65ca8a4f593a launched through the broker with the shared GPU lease, same sequence/seeds/budgets and one resident worker; frozen provenance in retries/openfold3_03. Repeats all36 requests to retain a consistent resident-worker comparison. GPU-level MSA consumption and resulting structural quality remain to be checked after the initial no-MSA cells. Biotin remains paused; no app code or release changed for this repair.

The retry03 saved native model configuration confirms3 recycles,1 diffusion sample, initial200 steps and the predict-preset MSA cap1024 (subsample_all_msa=true; subsample_main_msa=false). Dataset parsing accepts up to16384 rows; hence all8060 input rows are parsed before native inference subsampling. “Full MSA” means the full file with the unchanged native cap, not8060 simultaneously retained attention rows.

### GPU confirmation

Retry03 completed128-row/200-step seeds42 and43 successfully. Saved model-input features are[1,129,96,32] (native feature construction includes a separate query row); both have0 geometry violations/errors. Seed42 request28.6138s, core RMSD2.28006Å, core CA-lDDT0.89721; seed43 request28.4794s, core RMSD2.55984Å, core CA-lDDT0.89492. These are two individual observations, not final five-seed timing/quality summaries. All232 primary outputs and46 diagnostics present at this checkpoint pass the sequence/cardinality/finite-confidence audit. Refreshed figures; watcher job-65ca8a4f593a will refresh again at completion. Full-MSA native parser is verified; its GPU predictions remain pending at this checkpoint.

## Resident-request overhead review (2026-09-29 local)

User asks what lies outside model computation and how to speed it up. Read-only aggregation in experiments/sumo_model_matrix_exact_v1/review_request_overhead.py generates REQUEST_OVERHEAD.md and analysis/request_overhead.json from existing measured outputs (no new inference or changed matrix settings). Hardware: campaign Apple M4 Max64GB. Native diffusion/128-row MSA, five warm seeds per model: request/inference/median per-request gap seconds OpenFold28.718/13.893/14.753; Boltz7.058/4.881/2.177; IntelliFoldFlash9.397/6.575/2.841; Full37.814/34.919/2.905; Protenixv216.625/16.535/0.090; Mini0.896/0.794/0.102; Constraint12.146/12.060/0.085; ESMFull7.723/7.691/0.033. ESMFast sequence-only, four warm seeds:0.962/0.934/0.027. Medians are independent; do not subtract summary medians to infer the median gap.

Code findings: OpenFold recreates DataModule/DataLoader per request with10 workers; persistent_workers=True cannot survive replacement of that loader. Installed Lightning strategy teardown moves the cached model to CPU after Trainer.predict in both OpenFold and Boltz, with device placement on the next invocation; resident model-object identity does not establish continuous MPS residency. IntelliFold process_inputs measured2.451/2.512s (Flash/Full), and reloads ccd_v2.pkl per call. Boltz re-enters upstream CLI/Trainer construction, preprocessing0.251s; remaining gap is not yet partitioned. Protenix timing wraps runner.predict including to_device; these engine-specific inference boundaries are not measurements of exclusively GPU arithmetic.

Recommendations: test0/1/2 versus10 OpenFold data workers with preserved feature RNG; preserve a scoped session/device lifecycle; cache immutable IntelliFold chemical data and deterministic parsed input; bound CPU prefetch for directory/iterative requests. No speedup claimed for these proposals and no settings promoted. Individual spawn, CCD unpickle, transfer, writer and teardown costs are NOT separately measured yet. Same-seed feature/coordinate/confidence validation, mixed lengths, interrupted/resumed requests and memory checks required before promotion. Reference for macOS spawn/persistent workers: https://docs.pytorch.org/docs/main/data.html . Existing GPU benchmark continues unchanged; biotin remains paused.

## OpenFold and full matrix completion (2026-09-29 local)

Broker job-65ca8a4f593a completed all36 OpenFold requests:30 primary (five seeds per six conditions) plus6 diagnostics, one model load23.2236s, resident process838.3975s. Final report refresh audited250/250 primary predictions and50/50 diagnostics across all nine models; zero output-integrity audit failures. analysis_status.json matrix_complete=true. OVERVIEW.svg, REPORT.md, stage/structural figures and PROGRESS_SUMMARY.md refreshed from final outputs. The earlier detached report watcher had not refreshed terminal state; the terminal read-only refresh was run explicitly.

M4 Max64GB OpenFold200→25-step warm request medians/model medians/core RMSD medians (Å): no-MSA27.3518→16.8409s /13.6972→2.8979s /26.1571→14.4381;128-row28.7182→16.5164s /13.8932→2.8741s /2.3981→2.3708;full28.0032→16.7667s /13.6740→2.9942s /2.3672→2.3190. Core CA-lDDT1280.8889→0.8877;full0.8925→0.8908. Each scientific summary uses5 seeds; first no-MSA/200 timing excludes cold seed42 (4 warm), other timing cells5 warm. These are independently computed medians, not paired-difference statistics.

MSA features at model entry verified129 and8061 rows respectively (native separate query row),96 token columns; predict-preset internal cap remains1024. All20 MSA-enabled primary predictions have0 detected geometry violations. All10 no-MSA predictions flag core and whole-chain geometry and have poor crystal agreement. No-MSA output-integrity pass does not imply scientifically usable folds. Reduced diffusion saves about40–42% total MSA-enabled request time on this target while preserving similar core metrics; overhead remains13–15s/request. No global setting promoted; no worker/cache optimization applied in this matrix. Broader-target accuracy and overhead optimizations remain untested. Biotin remains paused.
