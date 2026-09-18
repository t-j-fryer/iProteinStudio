# 0030 — Biotin physical guidance and request grouping

2026-09-17; completed and audited. Full methods, failures, commands and evidence:
[project Lab Book0150](../../lab_book/0150-biotin-guidance-replay.md).

Hypothesis: pocket-only inference is cheaper but may compromise geometry;
request grouping may reduce overhead without changing scientific outputs.
M4Max64GB, macOS26.6.1;30 paired X-containing cycle00 initializations per arm.
Original job-002ee4e5c61e remains paused. Main job-1fdba14287be completed60 folds.
Starting commit f6ca4108e14dcebc7c60c3d3b77703098c9b45cd plus immutable working-tree
snapshot. All108 shared Boltz code/checkpoint fingerprints match source plan.

| Arm | s / initial structure | Contact + exposure pass | Correct ligand stereochemistry |
|---|---:|---:|---:|
| Original physical/FK on |48.69|13/30|30/30|
| Pocket-only singleton |15.48|11/30|19/30|
| Pocket-only one request |14.43|11/30|19/30|

Batching saved6.82% measured wall time here, with matching filter decisions.
Two resident workers, one model load each; contact guidance active; no affinity.
Only documented SVD CPU fallback warnings. Outputs are numerically close but
not bitwise identical; maximum aligned Cα/ligand RMSD0.0420/0.0783Å.

First pilot failed on a changed RDKit ligand conformer; corrected4-fold pilot
froze original preprocessing and passed. Main feature/RNG pairing passed for
all30 inputs. Empty-MSA YAML, original processed conformers, source/model/CCD
hashes, per-unit raw-artifact hashes, scripts and RNG states are retained.
Original timing includes initial preprocessing, replay timing reuses it.
No default promotion:11 pocket-only ligands have wrong stereochemistry, confirmed
by independent signed-volume checks. Four pass existing exposure/contact filters.
No reversed assessable protein Cα centres. One ligand, no timing repeats, fixed
arm order/native batch enumeration, incomplete side chains, no affinity or
optimization; no claim of biological binding. Full campaign remains paused.

Artifacts: `Validation/output/biotin_guidance_replay_v1/main/analysis`;
reproducible experiment under `Validation/experiments/biotin_guidance_replay_v1`.
