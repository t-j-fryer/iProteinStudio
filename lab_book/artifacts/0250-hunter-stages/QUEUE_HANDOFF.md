# Queue handoff: user-requested order, 2026-10-01

The user requested ESMFold2 Full 3 loops / 50 requested steps, MSA128, five seeds for all four priority-benchmark structures, AFTER the GPU tests in the Add NISE to iProteinStudio chat and BEFORE Protenix v2 citrate synthase resumes.

A dedicated watcher in `Validation/experiments/esmfold2_full_3_50_v1/queue.py` owns this handoff. Do not independently resume `job-bcaf0cacfdda` or `job-643a7569c927` after the acceptance tests. The watcher submits immutable ESM plan `plan-86082086db222eb5` through the shared broker, then resumes Protenix, then the binder screen. It holds no GPU lease while waiting.

Default gate: latest job receipt for each hunter_stages_v1 arm (including suffixed retries) must be completed and no other broker job may be queued/running/stopping. Failed tests are NOT treated as passed. If further GPU tests are planned beyond these three arms, coordinate before the last arm finishes; the watcher should be stopped until those additional tests finish.

If the test suite has finished with a documented failure or changed scope, the testing chat may explicitly release the queue by writing `Validation/output/hunter_stages_v1/gpu_tests_complete.json` with `{"gpu_tests_complete": true, "reason": "actual test disposition"}`. Write only when all intended GPU tests have finished. This does not imply tests passed.

Queue status: `Validation/output/esmfold2_full_3_50_v1/queue_status.json`. Benchmark plan and manifest are beside it. New ESM app defaults are NOT promoted automatically.

Protenix audit caveat: the interrupted five-seed block now spans resident sessions. Its existing strict single-session figure audit may reject the resumed results; preserve all outputs and disclose sessions or rerun a separately labelled homogeneous block. Do not silently treat the interruption as one resident session.

Acceptance update 20:10 UTC: core three routes and the Full interruption/resume test
passed. A final one-backbone ligand atom-mapping acceptance job-8b7126037d29 was
added after the benchmark watcher launched. It is queued behind the now-running
Full3/50 benchmark. Keep the existing watcher-owned Protenix/binder resumption;
the additional test uses the same execution lease. The implementation lab entry
is now0252 and Validation entry0077 to avoid concurrent numbering collisions.

Release-build note: production Swift compilation began around 20:27 UTC while
the separate Full3/50 citrate benchmark was on seed45. This is CPU/host work,
not another GPU inference job, but its possible host contention must be disclosed
when interpreting that block’s wall-clock timings. Functional output checks are
unaffected; do not present the overlapping block as an idle-host speed control.

Release handoff: watcher PID 68597 is temporarily SIGSTOP-held after verifying
its identity. The running benchmark and queued ligand test continue normally.
Resume this same watcher with SIGCONT after final tests and app/MCP staging;
it remains the owner of Protenix/binder resumption.
