# Biotin noising acceptance and requested campaign

The user authorized starting the terminal-oxygen-exposure campaign on 2026-09-17.
The full request uses the settings reviewed in project Lab Book entries 0140–0142.
Before starting it, run the five-start pilot through the immutable-plan bridge.

The pilot keeps the ligand, atom criteria, scoring, prediction protocol, sequence
designer and resident scheduler identical. It uses one trajectory, two optimisation
cycles, three first-cycle proposals, three ordinary proposals per parent, two
masked predictions and three repairs. It has at most 139 structure predictions.
It is an integration check, not an efficacy or throughput experiment.

`pilot_request.json` and `full_request.json` are the complete typed requests.
`manifest.json` declares acceptance conditions. Broker plans, model fingerprints,
job IDs, logs and the output audit belong under
`Validation/output/biotin_noising_acceptance_v1/`; actual immutable job outputs
are created by the bridge in Studio project `test2`.

The full 1,000-start request has a ceiling of 55,208 structure predictions.
Do not launch it on the strength of a merely successful job exit: the pilot must
reach cycle 2 and produce and evaluate a complete partial-noising repair. Record
failed gates or missing branch coverage explicitly, retaining their raw outputs.

`continue_after_pilot.py --state-dir Validation/output/biotin_noising_acceptance_v1`
can monitor the saved pilot and full plans. It requires pilot completion, successful
cycle-2 repairs, verified operation hashes, recomputed final atom/structure checks,
resident MPS/affinity receipts and the staged updated runtime before submitting
the exact full plan through `job_start`. It records a blocked status on any failure,
never retries with weaker settings, and stops if `STOP_CONTINUATION` exists in its
state directory. Full submission is idempotent through the broker. Guard tests:
`python test_continuation.py` from this directory. The watcher expires after 48 h.
