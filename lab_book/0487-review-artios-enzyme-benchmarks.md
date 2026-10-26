---
entry: 0487
title: Review Artios enzyme benchmarks and prospective search comparison
date: 2026-10-21
author: Codex
type: audit
status: complete
machine: Literature and source review only; no local inference or performance measurement
tags: [artios, motif-scaffolding, enzyme-design, beam-search, experimental-validation]
---

## Context

User requested review of the Artios research preview, its new benchmarks and tested
methods, and whether Studio's iterative sequence, greedy and beam search could be
showcased with a tractable laboratory validation. This is a research recommendation,
not a campaign launch or a promoted scientific setting.

## What was done

Read the 16-page main paper and relevant sections of its 28-page supplement,
including benchmark definitions, model comparisons, experimental campaigns,
methods and SeqVal reference table. Rendered and visually inspected main Figures
1/2 and supplementary benchmark definitions/Table 3. Queried the connected Studio
workflow guides, pipeline catalog and system detection. Inspected the canonical
checkout's CLI/NISE documentation, planner, RFD3 overlay and prior search audit
0414; checked the corresponding staged planner's protein-only motif guard.
No legacy Studio checkout was accessed.

Sources retrieved on 2026-10-21:

- Main: https://papers.ligo.bio/artios/paper.pdf
- Supplement: https://papers.ligo.bio/artios/si.pdf
- Landing page: https://papers.ligo.bio/artios/
- Main SHA-256: `05dde5273dc7cf39ab129077b00ce6a088a0e51637e27c8e63840e8d030fc575`
- Supplement SHA-256: `d784a0c8d95635b7f340623143c324a2309a232f59798b8ca34a3ed23cfdbd2c`
- Checkout HEAD: `be39339628202146c29fdd8809c23db491cdc6d2` (pre-existing dirty worktree).

## Results

**No new measurements — literature/source audit only.** All numbers below are
the authors' reported results, not Studio benchmarks. Their infrastructure uses
Modal CPU/GPU stages (main Figure 1 illustrates A100 80GB and A10G); exact per-arm
benchmark hardware, total inference cost and runtime are not established here.
Do not extrapolate their campaign timing to an Apple workstation.

### AME with additional ligand retention

AME originates with RFdiffusion2; Artios proposes stricter scoring, rather than
an entirely new motif collection. Main paper sections 3.1.1/7.4 and Figure 1:

- 38 of 41 specifications, 50 designs at each of 180/220/260/300 residues;
  200 per specification, 7,600 per pipeline (arithmetic from reported counts).
- AF2 backbone RMSD <2 Å, pLDDT >80; AF2 motif all-atom RMSD <2.5 Å.
- Additional Protenix co-fold check: every ligand centroid must be within 3 Å
  of its designed location after pocket alignment. Pocket residues have a heavy
  atom within 8 Å of any ligand atom in the generated reference structure.
- This last metric is a centroid displacement, not ligand heavy-atom pose RMSD,
  measured affinity, transition-state stabilization or evidence of turnover.

| Reported pipeline | Refold pass | Standard motif pass | With ligand retention | Specifications solved |
| --- | ---: | ---: | ---: | ---: |
| ArtiosBackbone + ArtiosPotts | 62.7% | 32.6% | 6.1% | 34/38 |
| Proteina-Complexa + LigandMPNN | 20.3% | 11.6% | 1.2% | 25/38 |
| RFdiffusion3 + LigandMPNN | 3.8% | 2.4% | 0.9% | 16/38 |

These change generator and sequence designer together. They do not isolate the
source of the advantage. The displayed comparison is not a greedy/beam/iterative
search ablation. RFdiffusion2 is historical context, not a fourth rerun arm in
this figure; Caliby is discussed but lacks a numerical arm in the displayed
SeqVal comparison. ArtiosPotts uses annealed Gibbs/MCMC sequence sampling, not
the Studio fold-redesign beam policy. Later experimental campaigns do include
ten-sequence redesign of selected backbones.

### SeqVal fixed-backbone sequence benchmark

114 curated single-chain natural protein-ligand complexes, roughly 100–700
residues and 1–4 ligands, derived from the AF3 Recent PDB holdout; ten sequences
per complex/model. Figure 2/Table 7 use backbone RMSD <3 Å, pLDDT >70 and every
ligand centroid <3 Å. At least one common passing sequence solves a target.
ArtiosPotts versus LigandMPNN: 23 versus 7 solved complexes and 104 versus 18
passing sequences. Switching the backbone check to AF2 gives 6 versus 0 solved
complexes, keeping the Protenix ligand check. The temporal split is relative to
the stated training cutoff; it does not prove absence of training overlap for
every newer model that Studio might evaluate.

### Material inconsistencies to resolve before claiming reproduction

1. Main AME: 200 designs across four lengths, 180–300. Supplement p16: 1,000
   across eight lengths, 200–340. Main says three specifications excluded;
   identities/reasons were not located in the inspected documents.
2. SeqVal Figure 2/Table 7: <3 Å and >70. Supplement section 3.2 prose: <2 Å
   and >80. Report both if doing sensitivity analysis; do not silently choose.
3. Main large-luciferase campaign: 9/45 active. Supplement Table 3: 1/48.
   Main butyrate campaign: 88 tested; supplement prose: 85 selected.
4. Main Table 1 explicitly records one million generated backbones for each
   experimental campaign. A small wet-lab panel is not a small computational
   search. No local forecast follows from the paper's approximate one-day claim.

The documents identify themselves as a research preview. The main text says code
is released, but a usable Artios source/checkpoint/benchmark download was not
verified in this review; the landing page links the PDFs without a code link.

### Current Studio fit and gaps

- Connected detection reports RFD3, MPNN, Boltz, Protenix and other current
  predictors as runnable. Detection is not a motif benchmark smoke test.
- The staged and source RFD3 planner explicitly reject non-protein targets for
  motifScaffolding/partialDiffusion. The underlying overlay has unindexed motif
  metadata, but the supported planner is not an enzyme-theozyme route today.
- Protein Hunter's sequence motif mode fixes identities, not 3-D motif geometry
  (docs/CLI.md, Native Protein Hunter region design). It cannot be labelled an
  AME implementation without additional geometry/mapping validation.
- NISE already has small-molecule search with a beam. Its affinity/confidence
  selection is not an enzyme objective; catalytic residue masks and fixed
  reference geometry must be carried through every proposal and prediction.
- AF2 and the supplement's Protenix V1 benchmark configuration are not exposed
  as exact choices in the connected catalog. Protenix v2/ESMFold2 substitutions
  constitute a Studio evaluation variant, not an exact paper reproduction.
- General greedy/beam protein search from Validation is not automatically a
  deployed native planner capability. Prior binder results do not establish an
  enzyme benefit.

## Decision and rationale

Recommend a paired search comparison first, with the central hypothesis:
**at equal compute, iterative search yields more independent families that retain
both the catalytic motif and substrate pocket, and more confirmed active enzymes.**

1. Establish the evaluator on frozen inputs and known controls. Preserve exact
   atoms, ligand identities/chemistry, residue mappings, original reference
   geometry and mandatory ligands. Missing outputs count as failures with reasons.
   Add centroid-preserving rotated-ligand and moved-motif negative controls.
2. Use a frozen, structurally varied SeqVal pilot (e.g. 20 targets chosen before
   looking at Studio results) to debug sequence search without generation cost.
   Keep comparison to the input backbone; report any structure-relaxing method
   separately from strictly fixed-backbone sequence design. Extend to all 114
   only after scope and evaluator are frozen.
3. For de novo motif scaffolding, generate identical RFD3 enzyme-motif roots
   for every policy. Compare independent LigandMPNN sampling; independent
   fold/redesign trajectories without cross-trajectory selection; greedy best
   parent; and a small diversity-aware beam (width four is a candidate, not a
   validated optimum). Use identical proposal model, masks, seed policy and
   predictor settings. Broader generator comparisons are a second experiment.
4. Equalize total scored proposals/predictor evaluations, then separately report
   actual end-to-end time including generation and independent assessment.
   Give the independent-sampling control the same compute budget. Do not compare
   equal cycle counts while the beam evaluates more proposals. Deduplicate exact
   sequences and count root families/structural clusters as well as candidates.
5. Start an AME engineering pilot with 8–12 predeclared diverse tasks at 180/220
   residues. This is not a full AME result. Complete 1–5 roots end to end before
   any new campaign over ten; then extend the frozen evaluation to the intended
   full task/length matrix. Log actual time and memory rather than forecast it.
6. Search with a model distinct from the final evaluator where practical. Freeze
   the finalist list before held-out assessment; repeated inspection and tuning
   against that assessor turns it into a selection model. Use original-reference
   motif/pocket checks, not only parent-to-child RMSD (which permits drift).
   Keep the paper's exact score separate from stricter chemistry diagnostics:
   ligand atom RMSD/orientation, catalytic distances/angles, clashes and pocket
   accessibility. High predicted affinity alone is not a catalytic objective.
7. Main figure: passing independent families versus measured compute. Supporting
   figures: refold→motif→ligand attrition, paired root rescue, structural diversity,
   and expression-normalized wet-lab activity of matched selected candidates.

### Laboratory recommendation

If luminescence equipment is available, a DTZ luciferase is the clearest first
functional showcase: direct sensitive readout, compact His/Arg motif, no metal
loading requirement. If fluorescence is the accessible assay, use a cysteine
esterase on 4MU-butyrate; this permits product calibration and quantitative
turnover, but matched expression-matrix controls and purified confirmation are
especially important for separating designed activity from background hydrolysis.

The main paper reports 7/85 initial DTZ hits and 17/88 butyrate hits; these are
external, differently selected campaigns, not predictions of our success or an
estimate of which reaction is easier to design. Prefer butyrate over starting
with octanoate or a metal-dependent phosphodiesterase. The supplement's use of
the word cutinase for octanoate hydrolysis does not establish polymer degradation.

For a first feasibility plate, compare independent sampling with the strongest
search policy after the computational four-way test: for example 32 distinct
root families per arm (64 designs), using the same expression/selection rules,
plus controls. This is a pilot, not a powered four-arm superiority trial; repeat
expression and assay measurements on separate plates as needed. Do not spend the
first plate on many near-identical descendants. A small paired baseline/descendant
subset can show rescue, but analysis must account for shared ancestry.

Include known active reference, no-DNA/empty-expression control, substrate-only
blank, and catalytic-site mutants for confirmed hits. Measure expression and
solubility separately from activity. Purify hits, repeat from independent
expressions, test substrate/concentration dependence, and show mutant effects
after controlling for expression/folding. For esterases demonstrate sustained
multiple turnover and calibrated product formation; a single acylation burst is
insufficient. For luciferases report calibrated/comparable photon output or
relative light and apparent kinetics; do not convert uncalibrated RLU to kcat.
HiBiT expression alone is a useful inexpensive process check but does not validate
motif geometry or catalytic function.

## Reproduce

Retrieve the two source URLs above, verify their SHA-256, and inspect main
sections 3.1/3.2/7, Figures 1–5, Table 1; supplement sections 3/4 and Table 7.
PDFs/extracted text/rendered pages are review intermediates under
`/tmp/artios-review/`, not scientific campaign outputs or committed artifacts.
Repeat connected `workflow_guide` for `rfd3_motif_scaffolding` and
`iterative_design`, `pipeline_catalog` and `system_detect`. Read the planner's
`rfd3_plan` guard, CLI region-mode contract and NISE objective before implementation.

## Limits and what was not tested

No inference, experimental validation, benchmark adapter implementation, statistical
power calculation, test run, Swift build, commit, campaign manifest, manuscript
edit or setting promotion. No claim that native AF2/Artios installation exists.
No confirmation of the authors' excluded AME IDs, exact runtime/cost, revised
supplement, atom mappings or available raw benchmark files. Lab equipment and
expression resources were requested but not yet established at time of writing.
Any executable experiment belongs in Validation with its required manifest,
immutable outputs, audit and both Lab Books, through immutable MCP plans.

## Next

Resolve source inconsistencies and obtain exact benchmark inputs/settings. Add
the minimum validated enzyme-motif/mask/evaluator route, then a controlled smoke
test. Choose DTZ or 4MU-butyrate based on actual laboratory capabilities before
ordering constructs. No campaign or purchase was initiated by this review.
