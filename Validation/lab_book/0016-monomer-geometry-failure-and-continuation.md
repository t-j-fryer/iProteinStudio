# 0016 — Monomer geometry rejection, expanded analysis and continuation

Date: 2026-09-06. Status: complete; final results in entry 0017. The following records failure diagnosis and continuation history.

The original screen stopped at 02:06:18 UTC in the sample-then-mask cohort.
Global trajectory 2 failed cycle-00 geometry: A:87–88 C–N=2.29 Å, above the
unchanged 2.2 Å gate. The frozen validator reproduces the failure. No normal
cycles ran for that seed. The failed job/raw outputs remain intact and no seed
is replaced. A supplemental audit verified its eight completed companions;
including the pilot this condition has nine complete of ten declared outcomes.

At 03:27:14 UTC there are 148/220 audited outcomes: 145 completed five cycles
(725 optimized structures), two variant-pilot initialization exhaustions, and
one geometry rejection. Thirteen full cohorts have n=10; sample-then-mask has
n=9/10. Eight other conditions still have only their pilots.

Sustaining antihelix, β and mixed priors raises sheet fraction relative to their
initialization-only counterparts by 6.3, 3.9 and 3.8 percentage points,
respectively. Sustained mixed also lowers confidence. Removing X masking gives
a larger sheet gain over β-only with a substantial coil increase. No
baseline-relative sheet advantage is established by the exploratory paired
intervals; no default is promoted. Full tables and intervals are in
`output/monomer_secondary_structure_v1/recovery_v1/reports/20260906T032714Z/REPORT.md`.

Read workflow_guide, system_detect and results_overview; diagnosed recorded job
errors before inspecting the rejected output. Verified unchanged model/engine
hashes and original source identities. The current runtime's seven campaign
files had changed; backed them up and restored exact originals while holding
an idle shared execution lock. Settings and frozen manifest remain unchanged.
The continuation executes only the eight pending conditions through their
original public Studio plans and normal audit gates. Supplemental failure
accounting is explicit and independent of the frozen original controller.

Continuation launched at 03:29:53 UTC, PID 11309, with 72 remaining trajectories
across eight conditions. First new job: `job-1dbffefc8810`, baseline_loopkill_1.
Launch identity and live progress are in `recovery_v1/controller_launch.json`
and `controller.log`. All three sustained-prior contrasts were independently
checked to have identical original sequences and P-SEA assignments in all ten pairs.

Hardware: M4 Max, 64 GiB, macOS 26.6.1. Base commit and dirty manifest, engine
and checkpoint hashes, exact commands and recovery receipts are recorded in
project [0099](../../lab_book/0099-diagnose-and-continue-monomer-screen.md).
MSA is empty; cached-MSA checksum n/a. Source and analysis are under
`experiments/monomer_secondary_structure_recovery_v1/`; every report records
its input audit hashes and source copies. Actual structural audit and report
generation ran; 725 optimized structures were reconciled from assignments and
confidence records. No model weights copied or settings promoted.

Untested/pending: eight full comparisons, completion of the recovery controller,
other lengths/models/seeds, experimental folding and default promotion.
