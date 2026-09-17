# 0028 — Biotin previous-parent partial-noising test

Date: 2026-09-17. Status: complete; branch acceptance passed. Hardware: confirmed Apple M4 Max / 64 GiB.

Hypothesis: a qualified parent from the previous completed biotin run can exercise
the actual masked-backbone and LASErMPNN-repair stages without repeating the
initial funnel that exhausted the preceding five-start pilot. No paired control,
efficacy inference, timing benchmark or default promotion.

Protocol and reproducible commands:
[`biotin_parent_noising_v1`](../experiments/biotin_parent_noising_v1/README.md).
Frozen plan `plan-3f997fd4df797b01`; job `job-3f997fd4df79`; output
`test2/nise_runs/nise-branch-0472093142998daf`. Source base
`92bdae1a1c4b547e6f3ab4bd851ffa6bea55c3e8` plus recorded working-tree changes.
The plan fingerprints scripts, model checkpoints, installed engine code and all
four imported input artifacts. Empty MSA, no cached alignment. Raw outputs remain
immutable; generated audit belongs in `Validation/output/biotin_parent_noising_v1`.

Parent `c06_t1_n0_s58`: strict geometry and current atom criteria recomputed/pass.
13 eligible residues, 3 masked per proposal, 2 proposals then at most3 repairs;
cycle2 policy, one resident worker. 44 software tests and `swift build` pass.

Real outcome: five folds, four affinity evaluations, three complete repairs, one
selected repair (`c02_t0_n999_s1`), score1.1774619 versus historical parent1.4353053.
One masked prediction failed O19 exposure and did not receive affinity evaluation.
All12 operation receipts/hash sets verified; one resident MPS worker crossed the
MPNN gap, structure/affinity load counts1/2, one allowed SVD fallback warning and
no other fallback. [Archived audit](../../lab_book/artifacts/0145-biotin-parent-noising/audit.json)
and [provenance](../../lab_book/artifacts/0145-biotin-parent-noising/provenance.json).

Selected repair Cα/ligand RMSD0.850/1.615 Å against its masked reference, but ligand
RMSD4.988 Å against the original parent. Both masked predictions would fail a
2.5 Å ligand gate if applied here; it is disabled by the cycle2 ramp. Thus this
confirms integration, not efficacy or later-cycle acceptance. No settings changed.
The preceding pilot failure remains in entry0027; full campaign still held.
See project Lab Book0145 for the full score table, limits and untested cases.
