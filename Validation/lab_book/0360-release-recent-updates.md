---
entry: 0360
title: Qualify Studio build81 and current shared workflows
date: 2026-11-04
author: Codex
type: audit
status: completed
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory
---

Manifest: experiments/studio_release_032_v2/manifest.json. Eight RFD4 routes and
two T4 prediction checks; existing immutable planner/broker path, pinned model
and runtime hashes, cached SUMO/scaffold MSAs for protein routes; ligand and T4
prediction MSA empty, no external MSA fallback. Output audits cover complete
receipts, cardinality, finite coordinates/objectives, chemistry/atom identity,
framework/conformer allocation, no unwanted affinity calls, and exact T4 kernel
parity without automatic reference generation. All raw outputs retained.

NESSO job-e0d6fb15dfc2 paused via supported cancel. Old failed build78 outputs and
draft remain held. Source/provenance and managed job IDs will be in preparation.json
and jobs.json. No efficacy or performance claim. All ten declared routes passed.

## Outcome and provenance

Build81 / MCP53, public source `e5100c2458ab93f61b76c7aca7aae9cea43cad1a`.
The initial600M job failed because its receipt consumer omitted pinned asset
identity; the fresh corrected job passed. No failed outputs or settings were
rewritten. The two snapshots differ only in the guarded600M receipt validator;
Full/Fast identity stays unchanged and is tested. Other routes retain their
original snapshots. `jobs.json`, `rerun-600/jobs.json` and `jobs_final.json` retain
that distinction.

Final audit: eight RFD4 routes (16 scored predictions plus two native-only T4
designs) and two one-sample T4 predictions. Exact paired T4 tensor/sequence equality;
no automatic reference generation. All jobs used caffeinate, the shared GPU
lease, immutable plan digests, pinned runtime/code, and retained memory summaries.
Model assets and environments were unchanged. Packaged scientific Python matches
the final snapshot; the only earlier-source reuse is documented explicitly.

Reproduction: use `studio_release_031_v1/prepare.py --request-file` with this
manifest and managed inputs; `prepare_predictions.py OUTPUT` submits the two
T4 controls. `audit.py OUTPUT` checks completed receipts, cardinality, finite
coordinates/scores, framework/conformer allocation, atom conditions, chosen
objectives and paired tensors. Outputs and original launch receipts remain in
`Validation/output/studio_release_032_v2`. The public qualification summary is
in Lab Book0743 artifacts and the GitHub release.

Not tested here: other Apple GPUs/OS releases, interactive VoiceOver, live PDB
network searches or Apple Gatekeeper/notarization. No new default, efficacy or
whole-workflow performance claim.
