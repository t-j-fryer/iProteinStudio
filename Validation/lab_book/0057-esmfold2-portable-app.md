# 0057 — Portable ESMFold2 app qualification

2026-09-28. Qualified; deployment verification follows in project0215.
Apple M4 Max,40-core GPU,64GB unified memory,macOS26.6.1. Source baselinebb408add8;
all modified inputs/scripts frozen in immutable MCP plans before inference.

Hypothesis: unchanged c26b9af MLX model code and tested Biohub CPU input/output
helpers can run in a relocatable portable package, with verified workflow handoffs.
Manifest and commands: `experiments/esmfold2_app_v1`. Immutable raw attempts:
`output/esmfold2_app_v1`. Complete audit, failed attempts, plan/job IDs, checkpoint
identities and limits are in [project0215](../../lab_book/0215-integrate-esmfold2-mlx.md).

Passed:12 offline Fast/Full monomer/complex/biotin inputs; per-input live publication;
interrupted directory resume without changing the first committed result; real
NESSO→Fast and PSICHIC→Full screening/folding/geometry/MPNN/later-request handoffs
with one retained model session each; real cached-MSA Full prediction; Predict
2-seed×2-sample cardinality/resume; RFD3 two-input result collection/resume.

Failures retained: first route harness passed None as MPNN designed-position text;
first RFD3 collection lost its outer request marker during native atomic rename.
The latter was fixed in the adapter and rerun successfully. Changed-input/output
and atom-map mismatch rejection are regression tested.

No new performance/default promotion. Historical timing numbers belong to0056 /
project0214. This does not validate ligand binding accuracy, full new generation
campaigns, other Macs or memory capacity, stereochemistry across broad ligands,
long-campaign stability, or MLX/PyTorch numerical equivalence.
