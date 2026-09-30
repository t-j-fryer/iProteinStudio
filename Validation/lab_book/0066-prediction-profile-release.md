# 0066 — Production prediction-profile acceptance

2026-09-30. Apple M4 Max / 64 GB; exact runtime identities captured in the broker
plan. This is release integration acceptance, not a throughput comparison.
Manifest and executable tests: `experiments/prediction_profile_release_v1/`.
New production profiles retain native Mini5/4, ESMFull100/20 and Fast50/3
sequence-only; other predictors use128 target MSA rows and25 steps. Underlying
qualification: project0228–0230 and Validation0060–0062. Current full campaign
has completed Boltz, Flash, OpenFold and Mini cohorts; Constraint is running.

Plan, input hashes, raw outputs, audits and failures will be recorded before
publication. No fresh-Mac or other-chip testing. Original paper job is preserved
and will resume after the shared-GPU acceptance window. Biotin stays paused.

Attempt01: plan84e8a86212123809 / job84e8a8621212. Raw output directory
`Validation/output/prediction_profile_release_v1/attempt01` contains the frozen
production scripts, manifest, two binder inputs, full SUMO MSA checksum and
runtime bindings. Serial execution started after the paper job released its
execution lease. Boltz and IntelliFold Flash each passed two audited predictions
at the time of this entry; other engines remain under test.


Final acceptance: all9 engines completed two different complexes (18 predictions).
`attempt01/output_audit.json` verifies recorded file hashes and finite confidence
JSON; native workers checked sequences, coordinates and geometry parsing.
No throughput comparison is inferred from these smoke measurements.

User steering supersedes the earlier resume policy: the original job stays
cancelled and immutable. New app-profile continuation plan
`plan-a36f3b69a4a992de` uses native Mini5/4 and ESMFull100/20. Source manifest is
the frozen `campaign_app_profiles_v1/frozen/config.json`; app profile SHA and
all runtime/model/MSA fingerprints are retained.2124 matching completed units
are imported through immutable receipt references;674 Mini1 outputs remain
only in the original cohort. The continuation uses the original instrumented
runtime so timing hooks and model versions do not change. Production integration
was checked separately in attempt01. Biotin remains paused.
