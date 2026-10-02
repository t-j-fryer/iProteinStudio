---
entry: 0272
title: Improve OpenFold residency and Figure3 scheduling
date: 2026-10-02
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

## Context
User requested app-wide OpenFold residency and continuation of Figure3 with one
structure worker, amortized CPU MPNN, and deferred common ESM assessment. Follow-up
to [0269](0269-audit-figure3-compute.md). The main queue is held at a quiet-host gate.

## Implementation and validation plan
Port Figure2a's scoped resident Lightning model and RNG-preserving zero-worker
feature preparation to the shared predictor registry. Route Predict directories,
RFD3 checking and Hunter cycles through that implementation. Keep native profiles,
MSA and seeds, validate receipts per input and publish results per prediction.
CPU MPNN keeps imports and checkpoint tensors warm but executes upstream main
unchanged per proposal, including model construction and RNG resets. Do not call
this a single permanently initialized MPNN model. Test cold/warm sequence equality.
Keep full Protenix v2's previously measured cycle-wave policy. Move common Full
assessment after native search and keep its session across cohorts. Retain original
raw outputs and timings; version all new execution provenance. Quiet-host waits
should wait rather than fail a campaign after ten minutes.

## Results
Pending actual tests; no new speed claims. GPU checks must use a frozen broker plan.

## Limits
No measurements yet. Tests must cover repeated inputs, settings changes, interrupted
work, several cycles, output cardinality and model identity before continuation.
Historical and revised execution timings must remain distinguished in analysis.


## Acceptance evidence (in progress)

- Swift build and all Swift request/results contract harnesses passed. MCP bridge
  23 tests, RFD3 scheduling 4 tests, Hunter stage 10 tests, new OpenFold receipt
  tests 5, and deferred Full session test 1 passed. The initial sandbox MCP test
  run lacked process visibility; rerun with required permissions passed.
- `figure3_residency_acceptance_v1`: CPU equivalence passed; cancelled while waiting
  for host load. No GPU prediction launched. v2 exposed old shell `find -type f`
  ignoring resident output symlinks after both cycle00 predictions succeeded.
  Fixed the normalized handoff and published real native artifacts in caller
  output folders. v3 was prepared but never launched. All snapshots retained.
- `figure3_residency_acceptance_v4`, job `job-0975269d6799`: complete. Two 60-aa SUMO
  binder trajectories × cycle00 plus five cycles =12 structures, six requests,
  one OpenFold model load. Ten optimization outputs passed chain, sequence,
  finite-coordinate and confidence/cardinality audits. No-work resume preserved
  all98 pred_min artifacts. Worker startup26.78s; full campaign134.21s. These GPU
  timings FAILED host-load qualification and are not a clean speed comparison.
  MPS driver allocation after each wave:2.725,2.713,2.712,2.745,2.747,2.673GiB.
  Peak accounted process-tree footprint9.409GB (not GPU memory alone).
- CPU MPNN's five cold/warm requests matched sequences exactly, including returning
  to the first seed after other requests. Matched seeds1042,1043,2042,2043,1042;
  temperatures0.3,0.1,0.3,0.1,0.3; same 60-aa backbone, SolubleMPNN, omitC.
  First calls3.439s cold/2.295s worker startup. Subsequent cold calls2.170–2.187s
  versus warm0.267–0.327s. Host qualification passed for this short CPU block on
  the M4Max. This is request startup amortization; not an inference-kernel claim.
  Raw results and host/memory traces are under the acceptance output folder.
- Functional deferred-check test confirms one load/one warmup across two cohorts,
  audited reuse, and rejection of changed saved structures.
- Paired replay of two saved 70-aa-binder legacy OpenFold inputs pending.

The executable no-work resume still loads a worker before finding all outputs
complete. This does not regenerate predictions; further lazy-load optimization
is deferred. No long multi-hour memory soak or broad ligand/nucleic-acid validation
is claimed. Model dependencies and weights are unchanged; no new install required.


## Paired-check seed discovery

The first paired harness stopped before inference due to a missing local import
path; v2 then ran two predictions but correctly FAILED the comparison: first
reference iPTM0.692931 versus requested-seed42 replay0.732626. Investigation found
every original Figure3 OpenFold output under `seed_2746317213`. The upstream
`InferenceExperimentRunner.update_config_from_args` uses `generate_seeds(42, n)`
when passed num_model_seeds, superseding query JSON seed42. This was not a numeric
regression. New app resident calls honour requested seeds; continuation explicitly
records OpenFold effective model seed2746317213, leaving MPNN/backbone seed42 and
data_seed42 unchanged. A new immutable paired replay uses that effective seed.
Do not pool requested-seed42 checks as a same-seed comparison to legacy outputs.


## Final validation and deployment

Paired `openfold_resident_paired_v3`, job `job-2f5cb31e597d`, passed both saved
70-aa-binder inputs with seed2746317213. Unaligned backbone RMSD0.0001312 and
0.0003275Å; absolute iPTM differences5.96e-8 and2.18e-5. One model identity was
retained across both requests; replay reused receipts without creating queries.
Per-input live records preserve original input names and all samples (unit test).

Rebuilt and codesign-verified local `build/iProteinStudio.app` (development build,
version0.2.20/build66), reopened it, and staged11 changed runtime/MCP helpers under
the exclusive execution lock with backups in artifacts/0272-openfold-residency.
Packaged resource contract passed, including both new worker scripts. No model
weights, Python environments or dependency downloads changed. No public release,
remote push or unrelated source commit was performed in this task.

Recursively audited181 existing cohort receipts:33 start cohorts (165 starts),
41 iterative cohorts (1025 refined outputs),74 assessment cohorts (1850 checks).
Created immutable continuation `plan-465040f858d224ef`; code is frozen under
Validation/output/figure3_sumo_design_v1_main_efficient1/frozen. It preserves
original scientific outputs, explicit legacy OpenFold effective seed, profiles,
MSAs and per-proposal MPNN RNG. Runtime revision is recorded on all new tasks.
The queue manifest `figure3_ordered_queue_v1/queue_efficient1.json` replaces only
the failed Figure3 entry; citrate and retrospective follow in their previous order.
Queue watcher launch is recorded in main_efficient1/queue_launch.json.

No end-to-end OpenFold speedup factor is claimed from the busy-host acceptance.
The CPU block provides direct measured startup-amortization evidence; long-run
throughput and host-qualified figure timing remain part of the continuing matrix.


Continuation job `job-465040f858d2` acquired the GPU lease, verified and reused the
completed cohorts, and reached `boltz_h1_l80_generate`. It is using the revised
host gate (brief wait, then explicitly unqualified timing if ordinary desktop
load persists), rather than failing as the previous coordinator did. Installed
resident helper hashes match the tested source. All original plan snapshots and
failed acceptance evidence remain available; no raw scientific outputs were edited.

Confirmed live continuation: the revised host gate advanced and submitted the
next five80-aa Boltz HK1 starts to its resident worker. Existing completed cohorts
were reused. No new error was reported at handoff.
