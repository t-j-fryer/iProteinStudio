# 0017 — Complete monomer control screen and output inspection

Date: 2026-09-06. Status: complete; no default promotion.

All 22 conditions and 220 declared trajectories are accounted for. There are
214 complete five-cycle trajectories (1,070 optimized structures), five
initialization-budget exhaustions and one retained geometry rejection. The
failed conditions complete at n=9 (sample-then-mask), n=8 (budget 1) and n=7
(coil length 8); the other nineteen conditions complete at n=10.

The completed controller report was generated at 05:50:37 UTC. A separate
read-only inspection reverified all 44 cohort audits/raw hashes, frozen code
identities, 1,289 cycle prediction records and 55 journal prediction records
(1,018 unique coordinate/sequence checks). Coordinate P-SEA, sequence, finite
confidence, geometry, all recorded initialization assessments and trajectory
aggregates reproduce. The single invalid geometry remains rejected. The first
analysis invocation had a filename collision with Python's `inspect` module;
renaming the script resolved it before successful execution.

Full proline suppression strongly favors helices: 71.7% helix, 7.8% sheet,
20.4% coil, mean pLDDT 90.0. Sustained priors give incremental sheet gains over
initialization-only priors, but sustained mixed has substantial coil and lower
confidence. No condition resolves a sheet-enrichment advantage over baseline
in the exploratory paired intervals. Masking has a larger effect than the
tested weak global biases or temperature changes.

Main β inspection accepts all ten with two extra predictions. Budget 1 drops
two starts; its eight survivors are unchanged. Coil length 8 drops three,
requires eleven extra predictions and leaves 0.1% mean sheet (0% at cycle 05).
Its apparent confidence gain is a survivor-selection effect: within the same
seven IDs, confidence falls slightly. Raising the confidence threshold to 70
has minimal additional effect. Coil confidence is separately analysed: extra
coil is not uniformly uncertain and is not a disorder diagnosis.

Means average cycles 01–05 within each trajectory, then trajectories equally;
cycle 00 is excluded. Paired bootstrap uses 10,000 resamples, without multiple-
comparison adjustment. This is one predictor, length and paired seed cohort;
no experimental folding validation, exhaustive sweep or default promotion.

Hardware: M4 Max, 64 GiB, macOS 26.6.1. Original base commit, dirty manifest,
exact engine/checkpoint/lock hashes and empty-MSA policy are unchanged and
recorded in the campaign receipts (cached-MSA checksum n/a). Full methods,
numbers, commands and limits: project
[0100](../../lab_book/0100-inspect-complete-monomer-benchmark.md).

Final artifacts:
`output/monomer_secondary_structure_v1/final_inspection/20260906T161423Z/` —
REPORT.md, inspection.json, trajectories.csv, all_controls.svg and PNG.
Inspector source: `experiments/monomer_secondary_structure_final_v1/review_outputs.py`.
No inference or raw-output changes were made during inspection.
