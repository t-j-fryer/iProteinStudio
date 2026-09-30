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

Final standalone acceptance also passed Boltz, Mini, v2 and Constraint (one
complex each), exercising the actual native CLI argument path at final defaults.
Plan `plan-73103e896403b4a3`, job `job-73103e896403`; four receipt hashes verified.
Combined production acceptance:22 predictions. The continuation's independent
export audit verified2124/5392 predictions with zero integrity errors. Final
Swift build, packaged resource checks, ad-hoc app signature verification and
Sparkle appcast generation passed.

## Publication and restart verification

Published `v0.2.17-beta` (build63), source commit `ec22920`, update-feed commit
`21d605c`. All four GitHub asset SHA256 digests match local artifacts. The live
Sparkle feed advertises build63; its archive signature was verified with the
project signing identity. Local app build63 is installed and opened, with
build62 retained under `build/app-backups/`. Installed MCP36 doctor passed;
all19 detected component entries report OK; prediction adapters match source.

Continuation `job-a36f3b69a4a9` is running under its immutable plan. First
audited Mini outputs confirm5steps/4recycles; full compute has not been reduced
on restart. Stage timing, geometry advisories and hash checkpoints continue.
The original benchmark job remains cancelled and raw results unchanged; biotin
was not resumed. The longer campaign and its comparative analysis remain in
progress. Distribution remains the existing ad-hoc trusted beta, not Apple
notarization or a fresh-Mac installation claim.
