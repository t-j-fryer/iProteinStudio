# 0025 — Fluorescein NISE score progression and adaptive subsets

Date: 2026-09-16. Status: complete; retrospective only.
Hardware: Apple M4 Max, 64 GB; CPU analysis, no inference or GPU timing.

## Question and controls

Before adopting 16→32→64 proposals with >0.01 stopping, how did the original
fluorescein Boltz score change, and where did advanced candidates lie within
64-proposal distributions? Paired within-cycle controls use the same historical
parent/proposals, geometry and ligand-pLDDT/100 + P(bind) score. Fixed 16, 32, 64
and adaptive 16→32→64 / 32→64 are compared with 2,000 permutations per group,
RNG seed 20260916. Threshold sensitivity includes 0.0001, 0.001, 0.005, 0.01.

## Provenance and audit

Source: `/Users/thomasfryer/NanoHunter/output/nise_fluorescein` (immutable).
Analysis HEAD: `04fcab788f46e0c53c96927757bb6e6388ba210d`, with uncommitted
analysis/default changes; exact extraction script is copied and fingerprinted.
Original checkpoint/runtime fingerprint: **unknown**, not inferred from current
installation. The saved config was overwritten by resume. Its 12 starts do not
represent the original 100. Empty MSA is verified in the saved candidate YAMLs;
all inputs have individual SHA-256 entries, rather than a nonexistent alignment
file checksum. Raw coordinates, sequence identities, ligand atom correspondence,
geometry eligibility and actual parent coordinates were audited and 21,807 source
hashes checked again afterwards. No raw outputs modified, no weights copied.

5,440 NISE folds = 85 groups × 64 proposals; six trajectories and beam one.
All 2,615 passing rows agree with recomputed geometry, and all 79 confirmed
advances select eligible maxima. 53 missing affinities occur in cycle five;
15 historical passing rows had pLDDT-only fallback scores. Missing combined
scores are not imputed. All six affected groups are excluded from simulations,
leaving 79 complete groups. Historical progression retains this missingness caveat.

## Results and decision

See [full report](../output/nise_fluorescein_adaptive_v1/analysis/REPORT.md),
[gallery](../output/nise_fluorescein_adaptive_v1/analysis/GALLERY.html), and
[project entry 0135](../../lab_book/0135-fluorescein-nise-adaptive-retrospective.md).

The median cycle has 32 eligible fully scored proposals and just one candidate
within 0.01 of the winner; winner-minus-passing-median is 0.171. Ten of 30
best-so-far gains above 0.0001 are at most 0.01. Trajectory peaks occur at cycles
8/3/2/13/9/20; the global winner's final two gains are about 0.0068 each.

Conditional adaptive 16→32→64 uses 56.35 proposals on average (12.0% fewer),
retains 92.3% of full-batch winners and loses more than 0.01 in 7.2% of decisions.
Adaptive 32→64 uses 58.39 proposals (8.8% fewer), retaining 94.5% of winners.
Actual-order 16→32→64 changes 5/79 winners; T3 cycle 10 loses 0.1062.
These are proposal counts, **not measured speedups**. Changes to advanced parents
would change all downstream proposals, so final-campaign quality cannot be inferred.
Four-cycle patience on the observed path loses T5's later 1.94325→1.95860 gain.

No adaptive policy is promoted. The user's explicitly requested defaults
1,000 starts / max 30 cycles / patience four are implemented as user choices.
Adaptive stays off; existing shared 0.01 tolerance remains pending a decision.
Recommend separating patience and top-up tolerances before any adaptive pilot.

## Reproduction and limits

[Experiment README](../experiments/nise_fluorescein_adaptive_v1/README.md) provides
commands. `config.json`, `manifest.json`, `audit.json`, `generator.py`, per-candidate,
per-cycle and per-trajectory CSVs accompany final analysis. A clipped first-plot
legend was corrected in the canonical `analysis/` outputs; original root-level
derived files were retained. No inference failure occurred because none was run.

One ligand and historical beam one only; missing cycle-five affinities, unknown
original checkpoint, related proposals, conditional parent paths. No prospective
paired full campaigns, model efficacy conclusion, beam-three, NESSO/RFdiffusion3
sampling test, restart/cancellation or memory soak. The 53 software tests, Swift
migration harness and app build check the changed contracts, not scientific efficacy.
