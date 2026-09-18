# 0032 — NISE stage-directory continuation and checkpoint recovery

2026-09-17; validation and launch verification passed; campaign ongoing. Project Lab Book
[0152](../../lab_book/0152-resume-biotin-with-stage-batches.md). Declared manifest:
[experiment](../experiments/nise_stage_batch_resume_v1/manifest.json).

M4 Max 64 GB, Boltz 2.2.1/MPS; original physical+FK on, stage-specific pocket policy,
3 recycles/200 steps/one output/seed 0/empty MSA. Two-input directory structure
request, intentional controller interruption after a native marker, recovery,
two-input affinity-head request, repeat resume without new inference. Declared
maximum four structure attempts and two affinity evaluations; immutable broker
plan, source/checkpoint hashes and shared GPU lock. No speed comparison or promotion.
Source commit `f6ca4108e14dcebc7c60c3d3b77703098c9b45cd` plus frozen source snapshot.

Successful smoke: `job-3a3397d12144`, plan `plan-3a3397d12144e480`, digest
`3a3397d12144e480c7ea71dc58f8534a53788a83533c26ff9736e065f3af5b35`.
Raw managed output: `test2/validation_runs/nise-batch-smoke-8321b43dee1f`.
Plan/status/overview: `Validation/output/nise_stage_batch_resume_v1/smoke2`.

Independent audit passed: one completed native structure per input; interrupted
unfinished work discarded; first completed input recovered without refolding.
One resumed structure request (one input), then one affinity request (two inputs),
then no additional inference on repeat resume. Four final operation receipts and
all referenced files verify. Resumed worker model-load count 1 then 2, MPS active;
two documented SVD fallback warnings and no other fallback. Intentional termination
produced a semaphore cleanup warning. Results overview returned no search rows;
this transport validation does not establish any binding hits.
[Audit](../../lab_book/artifacts/0152-stage-batch-resume/smoke-audit.json).

Failures preserved: a smoke preflight caught trajectory count above starts; corrected
the bounded fixture. `job-acbad6104a92` failed before model loading on a string/Path
entry-point mismatch; fixed and regression-tested before a fresh plan was launched.
Original campaign and 30 checkpoints remained unchanged during validation.

No long memory soak, full-funnel comparison or throughput claim. Pending request
membership changes future RNG streams; completed predictions are reused unchanged.
Production default scheduling remains unchanged. The user-authorized continuation
uses plan `plan-0f975ef0db89cf1a` with the original scientific config and output.

Continuation `job-0f975ef0db89` started successfully. At 23:47:14 UTC, its single
pending-stage request contains 970 inputs and one new audited checkpoint (`L155`)
is complete. All original 30 checkpoints remain unchanged: 31/1000 initial
structures complete. This is launch verification, not a completed campaign.
