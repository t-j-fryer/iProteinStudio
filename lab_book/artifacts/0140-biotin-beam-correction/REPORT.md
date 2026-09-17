# Biotin plan: two ordinary parents plus partial noising

Updated 2026-09-17 following the user's correction. Supersedes the provisional
chemistry requirement and 62,632-prediction ceiling in entry 0139.
**No campaign or pilot has been launched.**

## Ligand and atom criteria

Keep the previous **free-biotin** molecule and atom map. The user needs its terminal
section exposed; this is a sufficient specification for this screening objective.
Exact attachment chemistry is not a prerequisite for this campaign. It would
be relevant for predicting the particular conjugate's interactions or clearance.

- Bind: C31, S20, C29, C32, N24, C30, N23, O17, C21 (fused-ring head and its carbonyl oxygen).
- Expose: C25, C22, O18, O19 (terminal carboxyl region and adjacent tail carbon).
- Each Bind atom within 6 Å of a binder heavy atom.
- Each Expose atom retains at least 50% of its isolated-ligand solvent accessibility.

The exposed region is checked with a 1.4 Å water probe. This is an atom-accessibility
criterion, not a guarantee of clearance for an entire attached protein.
The saved Boltz atom-map signature was rechecked and matches the reference run.
See [labelled atoms](previous_biotin_atoms.svg).

## Sampling correction

The **ordinary sampling beam is two**, with one partial-noising branch. Internally
`beam=3` records the combined advancement capacity and `noise_advance=1` reserves
one of those places. It must not be set to two in the stored request: that would
leave only one ordinary place plus one repair. The UI calls this control **Total
sequences to advance**, with the ordinary/noising split displayed separately.

From cycle 2, rank all current parents by score (name breaks ties), use the best
two for ordinary MPNN, and separately use the best current parent for masking.
A repaired winner can become an ordinary sampling parent in a later cycle if
its score merits that position. Retain the best two ordinary candidates plus
the best passing repair. A failed repair branch leaves its reserved place empty.

| Per trajectory | Cycle 1 | Later full-beam cycle |
|---|---:|---:|
| Ordinary MPNN | 64 from the starting seed | 2 × 32 = 64 |
| Masked Boltz predictions | 0 | 32 |
| MPNN repairs of best passing masked backbone | 0 | 32 |
| **Total structure predictions** | **64** | **128** |

## Remaining settings

| Control | Value |
|---|---|
| Initial generator | Protein Hunter, 1,000 starts, 65–150 aa, 50% X |
| Initial refinements | Two rounds of 3 per retained lineage, one winner per lineage; first-round combined-score gate ≥0.80 |
| Unrestrained gate | 3 per lineage, Cα RMSD <2 Å and atom checks; all passing candidates advance |
| Expansion | 5 per gate survivor; 8 seeds from distinct original lineages |
| Optimisation | 8 independent trajectories; maximum 30 cycles; patience 4; improvement >0.01 |
| Noising | From cycle 2; 6 Å any-heavy-atom neighbourhood, 25% masked residues; 32 masked predictions → one passing winner → 32 repairs → one reserved winner |
| Score | Boltz ligand pLDDT/100 + P(bind) |
| Optimisation filters | Cα RMSD <2.5 Å; ligand RMSD <2.5 Å from cycle 3; atom checks throughout |
| Affinity | Geometry first; selective batches of 8; omitted for cycle00 and unrestrained gate |
| Execution | Resident Boltz; seed 0; empty MSA; steering enabled |
| Structure / affinity settings | 3 recycles, 200 steps, 1 structure sample / 5 recycles, 200 steps, 3 affinity samples |
| MPNN | Temperature 0.5; optimisation first-shell temperature 0.7, 10 Å Cα shell; existing Ala/Gly/Cys settings |
| NESSO / adaptive / apo checks | Off / off / off |

Initial refinement and expansion use atom checks without RMSD rejection. The
unrestrained gate and optimisation use the RMSD checks above. Partial noising
masks sequence identities, not coordinates; the whole structure can move and
the MPNN repair can redesign the whole binder. The settings remain experimental.

## Maximum scale

- Initial stages: **25,000 structure predictions**.
- Optimisation: 8 × [64 + 29 × 128] = **30,208**.
- Whole campaign: **55,208 structure predictions**.
- Separate loose affinity-head ceiling: **51,208 calls**, with 3 affinity samples per call.

These are arithmetic upper bounds, not runtime measurements. Attrition, incomplete
beams and four-cycle patience reduce the work; selective scoring reduces affinity
calls. Relative to ordinary beam-three sampling, noising now adds at most 32
structure predictions per later trajectory-cycle (7,424 for the full campaign).

The source implementation, UI budgets, MCP guidance and executed orchestration
fixtures use this accounting. No installed app or running snapshot was replaced.
The next execution step is a governed 1–5-start pilot reaching cycle 2, as required
by repository instructions, before proceeding to the full campaign.
