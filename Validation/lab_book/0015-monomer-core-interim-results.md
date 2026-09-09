# 0015 — Completed core monomer controls; wider screen ongoing

Date: 2026-09-05. Status: interim analysis complete; campaign running.

The 23:46:25 UTC snapshot contains all ten trajectories × five cycles for each
of baseline, helix kill, β prior, mixed and β inspection. Across the full
campaign, 67/220 trajectories have audited outcomes: 65 completed five cycles
and two additional inspection-variant pilots exhausted their budgets. The
remaining sustained-antihelix cohort is running; other full cohorts are pending.

Hypothesis tested: initialization priors and bounded inspection alter downstream
secondary-structure composition. Biotite P-SEA is measured on predicted
coordinates; cycles 01–05 are averaged within trajectory and cycle 00 excluded.

| Condition (n=10 each) | Helix | Sheet | Coil | CA pLDDT |
|---|---:|---:|---:|---:|
| Baseline | 44.0% | 18.4% | 37.5% | 83.5 |
| Helix kill | 30.2% | 19.1% | 50.7% | 71.1 |
| β prior | 61.0% | 6.4% | 32.6% | 82.4 |
| Mixed | 23.7% | 23.0% | 53.4% | 78.4 |
| β + inspection | 62.0% | 7.4% | 30.6% | 83.8 |

Mixed versus β-only adds 16.6 percentage points sheet (paired bootstrap 95% CI
7.5–25.8) and 20.7 points coil (7.7–31.9). Its 4.5-point sheet advantage over
baseline remains unresolved (−10.6 to +19.0; additional exploratory contrast).
Helix kill has lower mean helix, more coil and lower confidence. β-only does
not establish β enrichment. Inspection refined two starts once each, accepted
all ten, and reduced mean coil by 2.0 points with pLDDT +1.4; eight unrefined
trajectories matched the β control exactly. Intervals are exploratory and not
adjusted for multiple comparisons. These results do not promote a default.

Read results_overview, reverified all available audit/raw hashes, and
independently reconciled P-SEA and confidence summaries for 250 core optimized
structures. No campaign raw outputs or frozen scripts were edited. A separate
[analysis script](../experiments/monomer_secondary_structure_interim_v1/analyze.py)
creates timestamped JSON/CSV/report/SVG/PNG outputs. Current report is
`output/monomer_secondary_structure_v1/interim/20260905T234625Z/REPORT.md`.

Hardware: M4 Max, 64 GiB, macOS 26.6.1. Base commit
`37cc95497283025191e7d2067cb35d1af9168d72`; original dirty manifest, exact
engine/checkpoint/lock fingerprints and empty-MSA identity are preserved under
the campaign output. Cached MSA checksum: n/a. See project
[0097](../../lab_book/0097-analyze-monomer-core-controls.md) for commands,
manifest hash and full paired changes. No new runtime or performance experiment.

Untested/pending: full 17 additional comparisons, other lengths/predictors,
experimental folding, interaction sweeps and default promotion. No technical
campaign failure is recorded at this snapshot; two exhaustion outcomes remain
explicit scientific failures to progress.
