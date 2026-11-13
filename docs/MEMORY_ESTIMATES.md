# Review memory before starting a run

New app submissions show a Proceed/Cancel dialog after saving and validating the
run, before it enters the shared queue. The dialog shows this Mac's installed
memory, the largest planned complex and a prediction-stage peak estimate for
each matching engine/profile. Size includes every protein chain copy; design
uses the maximum configured binder length plus the complete target assembly.
Framework designs use the longest actual selected framework. Sequential folds,
seeds and design families do not multiply simultaneous memory use.

Cancel queues nothing. Proceed applies only to the reviewed immutable plan;
there is no app-wide override toggle. Model/settings/engine validation remains
active. The saved plan retains the existing explicit override policy so a legacy
memory restriction cannot reject a workload the user has just reviewed. Queued
and resumed jobs keep their saved policies. CLI/MCP planners continue to enforce
their existing admission rules unless their caller explicitly selects override.

## What the number means

The source is Lab0851's M4 Max40-GPU-core/64GB analysis,
`Validation/output/memory_scaling_models_v1/models.json`. Twelve process-footprint
fits/anchors are packaged unchanged with provenance hashes in the bridge's
`memory_estimate_models.json`. This package is retained in job code snapshots.

The planning peak is the fitted median of sampled warmed-request peaks, plus
the largest observed positive peak residual in that profile's reference data.
For example,500total aa with Full BF16 gives a typical peak of25.1GiB and a
planning estimate of27.4GiB. This allowance covers the observed request peaks;
it is not an upper confidence bound or a promise about unseen jobs. Loading,
other apps, different hardware and unmeasured settings may increase memory use.

Precision, chunk/cache settings, samples, MSA depth and model steps/recycles must
match a reference profile. Unsupported settings are marked unavailable. Size
extrapolation is explicitly labelled. Concurrent-worker scaling is labelled as
an unvalidated planning assumption; folds per model load reuse memory sequentially.
Selected engines are sequential prediction stages, so their estimates are not
blindly added. Uncalibrated initialization, sequence design and overlapping
resident stages make the overall workflow estimate partial.

RFD3/RFD4 allocator counters and historical RFD4 fits are not presented as total
RAM. Generation can therefore remain unestimated even when the subsequent
predictor has a useful estimate. Ligand/nucleic-acid profiles, custom annotated
motif sizes and other unmatched configurations explicitly remain unknown. The
user can still choose Proceed after reviewing that limitation.

## Saved evidence

- `studio_memory_review.json`: exact plan ID/digest, installed RAM, size/profile
  estimates, uncertainty, model-data and estimator hashes.
- `studio_memory_confirmation.json`: accepted review digest, timestamp and choice.
- `studio_job.json`: the queued job for that reviewed plan.

Changing the review or frozen inputs invalidates its confirmation. Existing
broker leases, pinned runtimes, checkpoint/resume and memory sampling continue
through the normal execution path. No engine settings are silently changed.

Lab0856 and Validation0414 record CPU/native-build qualification and its limits.
