---
date: 2026-09-17
status: in-progress
experiment: biotin_noising_acceptance_v1
---

# Biotin partial-noising acceptance

User-authorized campaign, preceded by a bounded integration pilot. No default
promotion or performance comparison. Apple M4 Max / 64 GB; empty MSA; installed
Boltz-2 structure and affinity checkpoints plus LASErMPNN. Source is the pending
build-38 tree; immutable broker plans fingerprint the exact executed scripts,
engine code and checkpoints independently of the Git commit.

The five-start pilot uses the same free biotin and head hotspots as the prior
test2 run, exposing only terminal O18/O19 at 50% retained SASA. One trajectory,
two cycles, three first-cycle and ordinary per-parent proposals, two masked
predictions and three repairs. Resident scheduler, geometry-first selective
affinity, no NESSO. Up to 139 structure predictions. Full request: 1,000 starts,
eight trajectories, 30-cycle maximum/four-cycle patience; up to 55,208 structures.

Plan `plan-8e5b6fae95094aa8`; job `job-8e5b6fae9509`; output
`test2/nise_runs/nise-3c9725ad1fee467f`. Managed job entered initial generation.
Acceptance requires audited cycle-2 masks and complete repairs, valid finite
outputs/atom checks, correct parent counts and resident loading evidence.
No timing or efficacy conclusion yet. Raw outputs remain immutable; all
inspection and final audit are recorded separately in Validation/output.

Configuration and protocol: `experiments/biotin_noising_acceptance_v1/`.
Plan/job receipts: `output/biotin_noising_acceptance_v1/`.
Project record: `lab_book/0143-biotin-launch-and-update.md` at the repository root.

Update: two of five initial backbones passed atom checks. Pilot was stopped
through the broker for build-38/MCP-19 staging, then resumed, reusing all five
initial predictions and the completed first refinement prediction. The installed
runtime matches packaged source `0128830`; running science retains its original
immutable snapshot. A detached guarded continuation audits the pilot before
submitting full plan `plan-bfd005780c66a3ef`. No full campaign submission or
scientific acceptance is claimed yet. State is saved in the experiment output
directory, including the maintenance stop/resume and continuation receipts.
