# Small AME motif pilot

Recommendation dated 2026-10-22. This is a prospective selection, not a result
or an executed campaign. The released dataset in Studio has **41 cases**, not
43. The exact 38-case Artios subset remains unverified. Use the pinned AME
fixed-ligand fixtures and source hashes already retained in the beta.

## Recommended order

| Priority | Case | Exact selected motif | Released ligand instances | What it tests |
|---|---|---|---|---|
| 1 | M0349_1e3v, ketosteroid isomerase | A16 TYR OH/CZ/CE1/CE2; A40 ASP OD2/CG; A100 ASP N/CA/C/CB; A103 ASP OD2/CG | DXC A801 | Four residues, 12 selected atoms; one organic ligand, no metal/cofactor. First complete test of insertion, sequence locking, template mapping and original-input recovery. |
| 2 | M0097_1ctt, cytidine deaminase | A102 HIS ND1/CG/CE1; A104 GLU OE1/CD; A129 CYS SG/CB; A132 CYS SG/CB/CA | ZN A296; DHZ A295 | Four residues, 10 selected atoms; metal geometry and preservation of catalytic cysteines in both sequence designers. |
| 3 | M0040_13pk, phosphoglycerate kinase | A39 ARG NH1/CZ/NE/NH2; A219 LYS NZ/CE/CD; A376 GLY N/CA/C; A399 GLY N/CA | MG A422; ADP A421; 3PG A423 | Four residues, 12 selected atoms; two organic ligands plus a metal. Challenges multi-entity bookkeeping, pocket/pose scoring and simultaneous placement. |
| 4, extension | M0050_1dbt, OMP decarboxylase | A33 LYS NZ/CE; A60 ASP OD2/CG/CB/OD1; A62 LYS NZ/CE; A123 THR OG1/CB/CA/CG2; A215 ARG N/CA/C/CB; B65 ASP OD2/CG | U5P A250 | Six residues, 18 selected atoms; motif spans two native chains. Tests mapping into one newly designed chain without confusing original numbering or recreating the original oligomer. |

Counts and selections above come directly from the pinned inventory, not from
full-residue atom counts. All four passed the existing installed CCD heavy-atom
set check. That check does not establish protonation suitability or activity.
References: [1E3V](https://www.rcsb.org/structure/1E3V),
[1CTT](https://www.rcsb.org/structure/1CTT),
[13PK](https://www.rcsb.org/structure/13PK),
[1DBT](https://www.rcsb.org/structure/1DBT).

Choose these before observing results; keep failures in the denominator. This
panel intentionally spans input/chemistry complexity and is not representative
of full-benchmark success rates. The expected difficulty order is a hypothesis,
not a measured property. In particular, faithfully reproducing ligand placement
in PGK does not establish domain motion or phosphate-transfer activity.

## Bounded execution sequence

1. One 1E3V root with `policies: ["fixed"]`, one cycle and one proposal per
   designer, one sequence from each designer, one guided proposal prediction
   and one separate untemplated check per sequence: four search-model prediction
   calls, plus generation/sequence design. Use the explicit memory override.
   Record actual memory, atom mappings, chemical identities, failures and output
   audits. Run this through the managed queue; no standalone GPU scripts.
2. Check the resulting motif RMSD to original input, per-residue errors under
   the same global fit, ligand centroid and pose diagnostics, local geometry
   and full-backbone confidence/recovery. Exact exported fixed atoms alone are
   not evidence of scaffold quality; retain pre-copy candidate RMSD.
3. Once the full route works, use the first three cases with two independent
   roots per case, both designers, all four policies, two cycles and four total
   proposals per arm/cycle (beam width four). This is a proposed budget of
   **384 sequence proposals and up to 768 guided/untemplated predictions**,
   excluding separate final assessment and generator work. Failures/extinct
   lineages can reduce completed counts; retain attempted counts. Two roots
   support debugging and exploratory comparisons, not a strong statistical claim.
4. Add 1DBT for the cross-chain mapping challenge. Under that same budget the
   four-case panel totals 512 proposals and up to 1,024 search-model predictions.
   Use observed first-case runtime/memory before committing to this expansion.
5. Keep all roots shared across arms; do not give one designer only the best
   root. Fix template source, sampling settings, seeds and ranking profile.
   Reserve template-source and extra-engine comparisons as separate experiments.
   A different predictor family evaluates a frozen shortlist without templates.

A Validation manifest, immutable raw outputs and both Lab Book entries are
required before starting a comparison or promoting measured settings. This
recommendation does not launch jobs or modify memory calibration coefficients.
Native Protenix/IntelliFold CPU feature checks passed, but only Boltz automatic
beta cycling is currently implemented.

## Laboratory priorities

My first assay candidates would be KSI and cytidine deaminase. Both have direct
spectrophotometric activity readouts described in primary experimental work:
[KSI continuous UV assay](https://www.nature.com/articles/s41467-018-03597-y)
and [cytidine deamination UV assay](https://pmc.ncbi.nlm.nih.gov/articles/PMC2910114/).
This is an assay-practicality judgement, not a prediction that either motif will
produce active de novo enzymes. UV-capable instrumentation and appropriate
substrate/reagent access should be confirmed before choosing a wet-lab panel.

The benchmark ligands are not interchangeable with activity substrates: 1E3V
contains deoxycholate; 1CTT contains a transition-state analogue. Reproducing
those pockets tests geometry/binding. Activity needs a separate actual-substrate
experiment, with native enzyme, no-enzyme and catalytic-mutant controls, and
product confirmation for promising hits. Keep a substrate-focused follow-up
explicitly separate from the fixed benchmark inputs.

If an NADH readout is a better fit for the lab, M0584_1ldm (four motif residues,
10 selected atoms; NAD A330 and OXM A331) is a useful later cofactor case. Its
fixture uses oxamate, not a turnover substrate. It adds substantial cofactor
geometry and is not my first software smoke test.

## Cases to defer

- M0024_1nzy, M0054_1qfe and M0731_1mt5: current CCD/fixture heavy-atom mismatches
  require explicit chemical variants. The earlier 1QFE smoke suggestion is
  superseded by this chemistry audit.
- M0630_1j79: only two selected protein atoms; the current global rigid-fit
  objective is underdetermined. It needs a separately qualified ligand-anchored
  definition, not a fabricated zero RMSD.
- Larger redox/cofactor assemblies and the rest of AME-41: broaden after the
  pilot demonstrates a working, resumable path and meaningful selection.
