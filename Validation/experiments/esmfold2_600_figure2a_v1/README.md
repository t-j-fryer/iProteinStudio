# ESMFold2-600 Figure 2a arm

Four exact original constructs/reference masks, one warmup then seeds 42–46 in
one resident model per block. Primary arm retains Figure 2a's 4 GiB MLX cache and
unchunked transitions. A separately labelled low-memory arm uses512 MiB cache
and32-token transition chunks. Both use3 loops/50 requested steps/one sample,
explicit sequence-only inputs. Eight blocks,40 measured requests plus8 warmups.

The original Profiler,0.5 s Darwin footprint/RSS sampler and crystal/geometry audit
are copied unchanged; `harness_sources.json` records their exact hashes.
The previously qualified host monitor requires three quiet 5 s observations and
flags sampled compilers or sustained externalCPU≥200%. Nested synchronized
stage timers overlap. MLX counters and process footprint are distinct measures.
The citrate synthase dimer is an explicitly declared research benchmark; this
experiment does not broaden the app's monomer-only beta workflow.

`prepare.py --repository REPOSITORY` freezes targets, code, protocol and a normal
Studio immutable plan. Launch its ID/digest through `studioctl.py start`.
Workers run only under the broker's exclusive lease and pinned runtime view.
The user-authorized memory override is recorded; no memory profile is promoted.
Never run `worker.py` or `run.py` outside the managed job.

Raw failures are preserved. A failed block stops its remaining seeds, with no
automatic reduction of size/precision/budget. Resume verifies completed hashes,
retains incomplete attempts, reloads one model and warms it before pending seeds.
No figure/manuscript replacement is automatic. No16 GB hardware or whole-model
CUDA parity claim; the four reference structures are training-era agreement tests.

The retained first attempt used an explicit environment assignment that bypassed
the broker view and was cancelled. Qualified results must come from the corrected
`esmfold2_600_figure2a_v1_retry2` directory and pass its runtime-view assertion.
The corrected manifest/plan and per-block load records pin the actual adapter,
runtime, checkpoint and encoder identities.
