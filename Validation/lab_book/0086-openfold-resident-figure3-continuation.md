# 0086 — OpenFold resident integration and Figure3 continuation

See [project record](../../lab_book/0272-openfold-residency-and-figure3-scheduling.md).
Status: implementation and paired acceptance checks pending. No changed science:
one structure worker, existing profiles/MSAs/seeds, CPU MPNN unchanged sampler,
common Full assessment deferred. Preserve all original outputs; separately label
new timing provenance. Controlled CPU and GPU checks recorded in immutable plans.


Completed acceptance: two trajectories × five refinement cycles plus cycle00,
one OpenFold model across six waves; all12 structures audited and98 saved
artifacts unchanged on resume. CPU SolubleMPNN cold/warm sequences identical for
five requests. Warm calls0.267–0.327s versus cold2.170–2.187s after first-call
startup, on this M4Max; CPU block qualified. GPU timings failed quiet-host audit.
Paired effective-seed2746317213 replays match old OpenFold coordinates within
0.000328Å and iPTM within0.000022. The old CLI had overridden query seed42;
remaining benchmark OpenFold work explicitly preserves its effective seed.
Full details/failures/tests/deployment in project record0272. Revised broker plan
465040f858d224ef and durable queue queue_efficient1.json preserve downstream jobs.
