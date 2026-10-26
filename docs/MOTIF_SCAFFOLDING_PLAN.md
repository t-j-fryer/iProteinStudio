# Transferable atomic motif scaffolding and search

Status: implementation plan, 2026-10-21. Input inventory audited; no new model
inference, production integration or scientific validation. See
[Lab Book 0488](../lab_book/0488-plan-transferable-atomic-motifs.md).

## Intended capability

Represent a motif once, generate scaffolds with RFdiffusion3, and carry the same
identities, atom selections, ligand chemistry, reference geometry and scoring
policy through sequence design and prediction cycles. Support protein motifs
alone, protein interfaces, and catalytic motifs with one or multiple organic
ligands, cofactors and ions. A target protein must be optional, not a prerequisite
for motif scaffolding. Accept motifs assembled from multiple source chains into
one designed chain. Keep fixed partner chains separate from transplanted motifs.

"Anything" means the modalities and chemistry supported by the pinned engine:
unsupported covalent/noncanonical inputs fail explicitly. Do not add DNA/RNA
generation without the separate checkpoint and explicit scope; its existing
unavailability is not solved by generalizing the request schema. Indexed and
unindexed motifs remain distinct. Do not promise arbitrary cyclic motif support.

## Exact benchmark inputs recovered

The original RFdiffusion2 AME release is pinned at
`d365cbf4db3958814a9f8e4f6f94fa309dfebc2b`:

- [Original specification](https://github.com/RosettaCommons/RFdiffusion2/blob/d365cbf4db3958814a9f8e4f6f94fa309dfebc2b/rf_diffusion/benchmark/mcsa_41.json)
- [Coordinate fixtures](https://github.com/RosettaCommons/RFdiffusion2/tree/d365cbf4db3958814a9f8e4f6f94fa309dfebc2b/rf_diffusion/benchmark/input/mcsa_41)
- [Fixed-ligand benchmark configuration](https://github.com/RosettaCommons/RFdiffusion2/blob/d365cbf4db3958814a9f8e4f6f94fa309dfebc2b/rf_diffusion/benchmark/configs/enzyme_bench_n41_fixedligand.yaml)

Local copies retain original bytes, atom names, coordinates and BSD license.
The [inventory review](../lab_book/0488-plan-transferable-atomic-motifs.md)
lists all 41 cases. [Bundled machine-readable inventory](../Sources/iProteinStudio/Resources/pipeline/scripts/motif_beta/data/inventory.json)
includes selected protein atoms, every source residue/ligand instance, complete
available reference atoms, coordinates and hashes. The executed audit verified
44 upstream files against Git blob hashes and resolved all selections:
172 motif residues, 524 selected protein atoms, 80 ligand instances; 30/41 cases
have multiple ligands. There are 56 distinct ligand component codes.

Examples (original source numbering, not future designed positions):

| Case | Exact protein conditioning atoms | Ligands |
| --- | --- | --- |
| M0054 / 1QFE | GLU A86 O,C,CA; HIS A143 NE2,CD2,CE1,CG,ND1; LYS A170 NZ,CE,CD | DHS A301 |
| M0097 / 1CTT | HIS A102 ND1,CG,CE1; GLU A104 OE1,CD; CYS A129 SG,CB; CYS A132 SG,CB,CA | DHZ A295 and Zn A296 |
| M0040 / 13PK | ARG A39 NH1,CZ,NE,NH2; LYS A219 NZ,CE,CD; GLY A376 N,CA,C; GLY A399 N,CA | ADP A421, Mg A422, 3PG A423 |

Preserve the distinction between two original configurations: `mcsa_41.json`
contains partial ligand-atom masks, while the published `fixedligand` override
clears those masks and disables ligand flexibility. Record both; never silently
translate one into the other. ORI pseudoatoms are generator metadata, not ligands.
Do not regenerate the curated coordinates from current PDB downloads or select
generic TIP masks: the released masks include backbone atoms and unusual subsets.

This is **exact upstream AME-41, not verified exact Artios-38**. Artios' excluded
three IDs and any modified masks/ligand treatment are still unidentified. Its
main/supplement sample counts and SeqVal thresholds disagree (Lab Book 0487).
Foundry's public validation config references a separate `mcsa_41.json` data
artifact not present in the inspected public tree. Searches did not locate an
Artios release manifest. Keep all 41; do not guess the excluded cases. Exact
leaderboard reproduction needs those artifacts/settings from the authors.

The coordinate audit does not establish chemical identity equivalence across
predictors. Before execution resolve each CCD component into bonds, formal
charges, stereochemistry and atom maps; freeze those records with hashes.
Choose explicit protonation/tautomer variants, and treat a change as a separate
scientific input. Metals remain separate components. PDB element/atom names alone
do not establish bond orders. The optional connected RCSB discovery plugin is not
installed; the original benchmark fixtures were obtained through GitHub.

## Engine capability and templating policy

| Engine | Current relevant capability | Planned motif-cycle role |
| --- | --- | --- |
| RFdiffusion3 MLX | Unindexed atom selection exists in the underlying adapter; Studio planner currently requires a protein partner for motif mode | Generate atomic motif scaffolds with optional partners and multiple ligands; validate all masks and mappings |
| Boltz-2 | Protein template guide, pocket/contact mechanisms; current target-template design API excludes designed chain A | Candidate for explicit mapped motif-template guidance; guide is not an atomic lock; untemplated ranking check |
| Protenix v2 | Protein template guide | Candidate for mapped motif-residue guidance and separate untemplated assessment |
| IntelliFold v2 Flash/full | Protein template guide through local A3M/mmCIF features | Candidate for mapped motif-residue guidance; both model variants require acceptance |
| Protenix Constraint v0.5 | Pocket and atom-contact features exist; inspected inference parser leaves `structure` substructure input as TODO | Experimental geometry/contact proposal route only after qualification; do not advertise working structure-motif conditioning |
| Protenix Mini, OpenFold-3-MLX, ESMFold2 Fast/Full | No supported Studio user-template route | Unconditioned cycling or assessment where exact molecular inputs are supported; clearly labelled as unguided |

The current connected catalog has guide templates, not a general motif policy.
Template embedders use residue/backbone/pseudo-beta geometry: passing side-chain
coordinates in a CIF does not mean catalytic tip atoms are locked. Existing
target-template controls must not simply be pointed at binder A and renamed.
Introduce a separate motif-guidance contract; retain existing target behavior.
Boltz strong coordinate forcing remains disabled after prior Apple-GPU failures.

For each generated root, build an explicit source→root→cycle residue mapping.
Use mapped motif residues' root backbone frames for template features, with
non-motif template positions masked. Do not import the full natural enzyme fold
or imply native motif backbone frames are mandatory when the original task fixed
only catalytic tips. A broader scaffold-template arm is a separate intervention.
Map by recorded indices, not fresh local sequence alignment: the surrounding
sequence changes and disconnected short motifs can align incorrectly. Never
concatenate fragments into an artificial peptide or lose inter-fragment geometry.

Each adapter returns requested/applied/unsupported conditioning with exact masks
and feature hashes. If the user requests templating, an incapable engine must
fail preflight; an untemplated arm is a separately declared policy. Feature-level
inspection must show that only intended query positions carry template evidence.
All independent validation uses complete sequences with no motif templates,
contacts, pocket restraints or coordinate copying.

## Shared immutable motif bundle

Version a `motif_bundle` containing:

- Source structure bytes/hash, source atom IDs `(model, chain, residue,
  insertion_code, component, atom)`, chosen altloc, coordinates and chemical state.
- Protein sequence-identity locks separately from coordinate conditioning atoms.
  Retain full available residue atoms for evaluation without making all of them
  generation constraints.
- Every ligand/ion instance with its atom graph, charge, stereochemistry,
  reference pose, conditioning mask and required evaluation atom set. Multiple
  copies of one CCD code remain separate instances with recorded assignments.
- Indexed/unindexed placement, motif group relationships, optional fixed partner
  chains, designed polymer length and actual upstream component/token accounting.
  Explicitly verify protein length after generation; do not equate length with
  ligand atoms or source residue numbering.
- Per-root generator insertion mapping and immutable root reference; per-cycle
  identity mapping, current structure and complete lineage. Subsequent cycles
  must not redefine the reference geometry to hide gradual drift.
- Engine guidance policy, sequence-designer constraints, scoring profile/version,
  search budget, seeds and software/checkpoint hashes.

RFD3 compilation combines `unindex`, explicit `select_fixed_atoms`, ligand
selectors and optional fixed-chain contigs. Do not duplicate ligands in both
`ligand` and contig. Disambiguate source-chain collisions before compilation and
preserve reverse mappings. Validate every expected ligand count and atom set
after generation, sequence preparation and prediction. Never copy motif/ligand
coordinates back into a prediction before scoring it.

## Metrics and proposed search objective

Retain separately named metrics:

| Metric | Definition and reference |
| --- | --- |
| Source motif recovery | One global rigid fit over the explicitly selected source functional atoms, matched to predicted atoms; never fit each residue separately |
| Full motif residue recovery | All required heavy atoms of mapped motif residues compared with the immutable generated root; exact paper fitting convention requires author/code confirmation |
| Ligand retention | After a single fit of the frozen root pocket to the prediction, displacement of each ligand heavy-atom centroid; pocket residues selected within 8 Å in the root |
| Backbone self-consistency | Unconditioned prediction versus immutable generated root, with declared backbone atoms and fit |
| Chemistry diagnostics | Symmetry-aware ligand heavy-atom pose RMSD without fitting ligand separately, catalytic contact distances/angles, clashes and per-ligand completeness |

Resolve symmetric protein/ligand atom naming using declared chemically allowed
permutations. Do not use arbitrary reassignment to hide a failed pose. Missing
ions/ligands/atoms, nonfinite metrics, changed motif identity and degenerate fits
fail explicitly. In particular, missing ligand slots cannot count as passing.

The paper-like final pass is a conjunction: backbone RMSD <2 Å, protein pLDDT
>80 on a 0–100 scale, motif all-heavy-atom RMSD <2.5 Å, and **every** ligand
centroid displacement <3 Å. The original RFdiffusion2 release uses different
evaluation (Chai-1 and a stricter motif threshold); do not conflate those versions.
Exact Artios AF2/Protenix V1 scoring is not available as a native installed route;
substitution is `studio-ame-v1`, not an exact Artios benchmark reproduction.

Proposed ranking, to freeze before the pilot:

1. Reject invalid identity, missing chemistry, severe clashes and failed output
   audits. Qualifying fold confidence/self-consistency is a gate; bootstrap any
   rescue allowance explicitly, rather than silently relaxing it.
2. For fold-qualified candidates let `m` be the declared full-motif RMSD and
   `d` the **maximum** ligand centroid displacement. Minimize
   `q = max(m/2.5, d/3.0)`, with lower sum of those normalized terms as a tie-break.
   All geometry-passing candidates (`q < 1`) therefore outrank geometry failures.
3. Preserve source functional-atom geometry as an additional guard with a
   separately registered tolerance; report this stricter scientific gate apart
   from the paper-like pass rate. Inspect pose/contact diagnostics because a
   reversed ligand can retain its centroid.

This is a proposed selection rule, not a validated accuracy improvement. For
motif-only tasks omit the ligand term explicitly; never fill it with an invented
zero. Do not use an average across ligands or pool pLDDT scales across engines.
Do not make affinity the primary enzyme objective.

Score **untemplated search-model checks** for advancement; otherwise a restrained
prediction could win simply by obeying the template. Guided predictions can
propose structures, but their copying compliance is not independent evidence.
Reserve a different model family for final evaluation on a frozen shortlist.
Count both guided and untemplated predictions in the compute budget.

Greedy retains one eligible parent per root. Beam retains up to a declared width
(four is an initial candidate) with duplicate suppression and diversity among
similarly scoring candidates. Both use the same eligibility/ranking code. Keep
an immutable best-so-far archive. Rank offspring against the original reference,
not only the previous parent; record extinct roots, failures and exhausted budgets.
Do not let an unsuccessful parent silently migrate to another root family.

## LigandMPNN versus LASErMPNN

Run a crossed comparison on shared RFD3 roots: four search policies (independent
sampling, independent iterative trajectories, greedy, beam) × two sequence
designers = eight arms. Begin with one qualified cycling predictor and the same
final assessor. Templating on/off and extra cycling engines are later separate
contrasts, not a confounded initial matrix.

Use identical catalytic identity locks, complete ligand/cofactor sets, coordinates,
chemical state, proposal counts, random-seed schedule and fold settings. Fixed
sampling from the original backbone gets the same total budget as search. Keep
proposal/fold counts and measured complete elapsed time as separate axes.

Concrete adapter work required:

- LigandMPNN already accepts `fixed_residues_multi`; explicitly qualify fixed
  side-chain context and any optional packing policy.
- LASErMPNN supports `--fix_beta` (B=1 fixed sequence/rotamer, B=0 design).
  The current RFD3 wrapper instead prepares `--designed-positions all` and does
  not pass `--fix_beta`: it is not an enzyme-motif-preserving route yet.
- The current LASErMPNN preparation helper expects one ligand residue name,
  renames/rechains atoms and accepts one SMILES. Replace this assumption for
  the new route with per-component chemistry and a durable atom bijection;
  preserve each ion and ligand instance. This is necessary for 30/41 cases.
- LASErMPNN needs explicitly protonated ligand input. Add hydrogens from the
  frozen chemical graph without changing benchmark heavy-atom positions.
  LigandMPNN may consume a heavy-atom view of the same graph. Do not combine
  unrelated ligands into one guessed molecule.
- Preserve catalytic cysteine even when the designer excludes C at designable
  positions. Prove masks/identity retention after every proposal; do not repair
  mutated residues after scoring.
- Match fixed motif side-chain context as closely as supported and disclose
  any difference. LASErMPNN jointly handles sequence/rotamers, so a full-residue
  rotamer lock is stronger than a tip-only generation constraint. Outside motif
  residues, use each method's documented native behavior and declare it.
- Do not rank different designers by their internal likelihoods. Use the common
  untemplated structural evaluator. Temperature is not calibrated between models:
  report native settings and, separately, an equally budgeted tuning experiment
  on development cases. Do not tune on held-out evaluation outcomes.

## Implementation and acceptance order

1. **Data contract and compiler:** introduce the bundle/schema, per-component
   chemistry and canonical mappings; extend the planner, preparation and result
   schemas without changing old saved runs. Keep source-vs-runtime provenance.
2. **Metric evaluator:** rigid-transform invariance, residue renumbering,
   symmetric atoms, missing ions, repeated ligands, rotated-but-centroid-preserved
   ligands, cross-chain motifs, nonfinite coordinates and degenerate fits.
3. **RFD3 routing:** motif-only, motif+one ligand, motif+ligand+metal,
   multiple-ligand and protein-interface fixtures. Inspect input/output masks
   and actual polymer length with the pinned MLX adapter.
4. **Sequence designers:** ensure fixed identities/required rotamers and atom
   mappings survive both adapters. Include the 1CTT cysteine+zinc fixture.
5. **Cycle guidance:** implement explicit position mapping and sparse template
   features for Boltz, then Protenix/IntelliFold if accepted. Negative control:
   the same sequence without template; no validation template leakage.
6. **Search:** shared greedy/beam objective, deterministic ancestry, compute
   accounting, duplicate handling and interruption/resume tests. No scores from
   incomplete outputs. Retain the shared execution lock/resident scheduler.
7. **Managed inference smoke:** 1–5 roots through the entire route. Suggested
   chemistry tiers are M0054/1QFE (single organic ligand), M0097/1CTT (ligand+Zn),
   M0040/13PK (two organic ligands+Mg). These are engineering fixtures, not a
   claim of easy enzyme activity or a substitute for the full benchmark.
8. **Prospective study:** freeze the eight-arm manifest, input/engine hashes,
   evaluator and denominator; record both Lab Books and audit immutable outputs
   under Validation. Full AME-41 and the verified Artios subset remain separately
   labelled datasets. Include failures and uncertainty over independent roots/tasks.

Before any commit, run relevant functional tests and `swift build`. No execution
plan, job, model installation, background inference or purchase is authorized by
this planning artifact itself.
