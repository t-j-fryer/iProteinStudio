# 0194 — LASErMPNN CPU residency qualification

2026-10-15. Complete. See project [0430](../../lab_book/0430-qualify-lasermpnn-cpu-residency.md).
Protocol: four saved prepared biotin complexes, fresh vs resident1/2/4 CPU workers,
threads1/2, one/five designs each, two alternating repeats,240 total sequences.
Compare full FASTA/score identity under explicit post-load RNG reset, wall time,
request/load time and RSS. Source/input/weight hashes frozen by prepare.py; no MSA.
No GPU inference, no production settings promotion; overlap remains untested.

Managed plan1b40ef9e51ca8266/job-1b40ef9e51ca submitted2026-10-15T23:07Z,
waiting for existing benchmark's execution lease. Output
`output/lasermpnn_residency_v1/20261015T230737Z`. Four CPU contract tests passed;
neural/speed results pending. HEAD25b3eb92dae59b4f4e48f3f10f7d6b8607faeb3d,
exact changed experiment/upstream hashes frozen in plan provenance.

Completed after watcher released execution lease2026-10-15T23:38Z. All240 outputs
match exact FASTA/score bytes. Elapsed seconds repeats0/1: fresh48.27/46.58,
resident1=12.21/12.24, resident2=9.21/9.14, resident4=7.99/8.20,
resident2_threads2=8.59/8.59. Includes startup/teardown on M4Max64GB. No default
promotion; overlap remains separate. See results.json in the recorded output.
