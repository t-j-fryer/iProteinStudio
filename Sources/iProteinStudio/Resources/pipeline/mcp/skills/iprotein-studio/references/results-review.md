# Retrospective results and viewer exports (bridge61)

Read `results_overview` first. `results_review` selects saved hits or applies
custom AND metric rules, sorting and per-family caps without rewriting original
verdicts. Protein defaults prefer `ipsae_min`; small-molecule defaults use
`boltz_combined_score` = P(bind)+ligand pLDDT/100 from the same assessment.
Missing/nonfinite metrics cannot pass a rule. Restrict `predictor`/`role` for
like-for-like comparisons; inspect `metric_sources` rather than pooling model
families. Cycle medians precede retrospective filters/caps, include recorded
proposals and retain separate predictor/role/context series.

Page with `limit`/`offset`, preserving the returned `snapshot_sha256` after the
first page. Changed snapshots require restarting the review. `results_review_export`
exports every match (not just a page) as sequence/score CSV plus review JSON in a
ZIP. Recorded missing sequences stay blank. Use `export_read`, verify chunk and
whole-archive hashes, then deliver the actual file to the user.

For contacts/burial, choose exact IDs from `candidates_list` and inspect the exact
coordinate artifact's author chain/residue or ligand atom names with
`target_inspect`. Do not reuse input-SMILES indices or assume A/B chain roles.
`results_spatial_plan` takes1–100 IDs, snapshot, artifact index and policy. Protein
proximity measures nearest selected binder heavy atoms to each target residue;
ligand proximity uses exact predicted atom names. Every/any compares maximum/minimum
nearest distance, inclusively. Burial is whole-ligand SASA relative to the same
isolated conformer, using the existing1.4Å RDKit FreeSASA protocol. Requiring
geometry checks the original hash-verified exact-pose receipt; it does not invent
or rerun a linker classifier. Missing sites/receipts cannot pass.

Review the immutable CPU plan and start authorized analysis with `job_start`.
This uses the shared queue and retained analysis environment, not a predictor.
Resume interrupted work through `job_resume`. Pass the completed job ID as
`spatial_job_id` in result review/export. Only selected passing poses match;
changed snapshots or corrupt receipts are rejected. These geometric/confidence
criteria are computational evidence, not experimental binding evidence.

`viewer_script_export` bundles one selected coordinate artifact and a hash-bound
manuscript-style Python script for ChimeraX. Retrieve with `export_read`, extract
together and open `manuscript_style.py` in separately installed ChimeraX. Optional
`emphasized_chains` must be explicit; the bridge does not start an app or upload
coordinates. A manuscript camera/cutaway is not reproduced automatically.

`memory_estimate` reports fitted assumptions/unknowns for a saved immutable plan.
It does not authorize overriding admission. Headless plans keep their explicit
memory policy; the app records per-submission Proceed/Cancel consent. Estimates
are measured M4 Max footprints, not installed-RAM guarantees on every Mac.

For CLI access discover `studioctl tools --profile run`, then invoke the same
schemas using `studioctl call TOOL request.json --profile read` (or explicit run).
Admin remains separate. Do not substitute direct scripts for broker execution.

Bridge61 preserves the explicit memory policy for composed recipes too. Supply
it at the tool request level; inspect the returned normalized policy in the
immutable plan. It does not belong inside recipe parameters.
