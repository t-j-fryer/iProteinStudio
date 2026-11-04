# 0355 — Studio 0.2.32 technical release acceptance

2026-11-03. Apple M4 Max, 40-core GPU, 64 GB unified memory. In progress.

Manifest: `experiments/studio_release_032_v1/manifest.json`.
Fixtures: historical public SUMO target/cached alignment; propan-1-ol with two
explicit torsions. No efficacy or speed comparison. Controls are unchanged
upstream/model defaults and earlier qualified routes; tests exercise new input
allocation and objective plumbing. Unchanged model/checkpoint, code and MSA
fingerprints are captured by each preflight and retained under the output root.

Launch uses the existing `studio_release_031_v1/prepare.py` with `--request-file`,
`--project studio-release-032`, `--run-prefix release032`, `--start`, and the public
candidate as `--source`. It verifies caffeinate, shared resource class, immutable
code and runtime bindings before job_start. No new GPU launcher, changed thread
controls, bypassed lock or active manuscript modification.

Raw jobs and all failures remain immutable under the managed project. Preparation
and audit evidence: `Validation/output/studio_release_032_v1`. Output audit must
verify receipts, cardinality, finite structures and objective values, framework/
conformer identity, ligand annotations and absence of affinity for ESM routes.
Publication awaits all six outcomes. Cancellation/restart behavior has fixture
coverage, but fresh interruptions of these six GPU routes are not planned.

The first framework route queued successfully. The first ligand request was
blocked by import-root policy; its raw request is retained. A separate managed-input
preparation ledger uses the same scientific fixtures copied into the owned project.
The audit combines both ledgers; no global import policy change was made.

## Final delivery follow-up

The original failed acceptance attempt remains intact. Validation0360 and Lab
Book0743 record the corrected source and all ten passing final routes. Published
`v0.2.32-beta`, build81 / MCP53, from `e5100c2458ab93f61b76c7aca7aae9cea43cad1a`.
The earlier build78 draft was replaced only after the new acceptance passed.
