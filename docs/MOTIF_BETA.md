# Atomic motif beta

Choose **Design → Motif scaffolding → Atomic motif beta · template-guided Boltz**.
The RFdiffusion3 screen also retains an **Atomic motif beta** button. This opens a
separate workbench with all 41 released AME cases, exact protein atom masks,
separate ligand/cofactor instances and bounded 1–5-root requests. The local
development build is produced by `build_app.sh debug`; it does not replace the
installed application.

**Execution status:** memory admission still lacks qualified RFdiffusion3,
ligand-complex and guided-prediction profiles. It blocks these by default, but
users can now enable **Override memory check for new runs** in the workbench
or Settings → Memory. The choice is saved with the job, and managed commands
record sampled memory usage. A bounded KSI test now passes end to end: one
RFD3 root, LigandMPNN and LASErMPNN, one fixed cycle, four guided/untemplated
Boltz predictions, and actual cancellation/resumption with unchanged completed
files. Neither candidate passed the unchanged geometry gates. This does not
qualify all cases, search policies, independent-family assessment or enzyme
activity. See [Lab Book 0579](../lab_book/0579-qualify-and-release-studio-027.md)
and [Validation 0259](../Validation/lab_book/0259-studio-release-027.md). Other
preflight checks remain active. See [memory policy](MEMORY_SAFETY.md) and the
[recommended small pilot](MOTIF_BETA_PILOT.md).

## Template choice

The benchmark fixtures come from natural enzymes. All 41 released fixtures
contain N/CA/C/O for every selected residue, plus ligand coordinates; only a
subset of the protein atoms is selected as generator constraints. The UI links
each case to its original PDB entry. The complete native 13PK structure was also
tested: extracting its selected residues preserves the benchmark geometry.

**A generated backbone is not needed to write a valid motif PDB/mmCIF.**
Disconnected residues can supply a sparse protein template. Prediction still
requires a complete query sequence and an explicit placement of each motif
residue in that sequence. A folding predictor does not automatically choose
the intervening sequence, length or motif order. Isolated catalytic tip atoms
cannot supply the backbone frames required by these Studio adapters.

The UI offers two sources of motif residue geometry:

- **Generated RFD3 residues** (default): retain the root's insertion map and
  motif residue frames. This allows RFD3 to find backbone placements compatible
  with the selected functional atoms.
- **Original benchmark residues**: retain original motif N/CA/C/O and available
  side chains, mapped to the same query positions assigned by RFD3. This imposes
  native residue geometry beyond the benchmark's selected atomic constraints;
  compare it as a distinct intervention, not an identical benchmark condition.

Both supply no coordinates outside motif positions. A separate CPU exporter
also accepts explicit query positions without any RFD3 root, and can extract
the selected residues from an actual native PDB/mmCIF with the original
chain/residue identifiers. Imported coordinates remain in one common frame;
they never replace the benchmark's reference coordinates or ligand chemistry.
Never replace the immutable original atomic motif used for scoring with a
later predicted structure.

- **Boltz-2:** a full-length query polymer sequence in mmCIF, with coordinates
  only at mapped motif positions. The native parser can realign sparse residues
  to wrong positions in repeated sequences. The beta now uses
  `motif_beta.boltz_templates` to honor explicit `label_seq_id` in marked files,
  retaining native atom parsing/masking and ordinary-template behavior. All 41
  cases passed CPU parsing with this adapter; a native YAML test also verifies
  template-to-query matching. **These exports require the Studio adapter; do not
  pass them to unmodified Boltz and assume positions are preserved.** The beta
  resident installs it with one preprocessing worker. No coordinate forcing.
- **Protenix v2:** explicit `queryIndices` and `templateIndices`, avoiding a new
  sequence alignment after every mutation. Native CPU feature generation passed all 41 cases with exact sparse
  query correspondence using installed Protenix 2.0.0. Model inference remains
  untested.
- **IntelliFold v2:** a local mmCIF plus an A3M with exact query columns and gaps
  everywhere outside the motif. Native CPU feature generation passed all 41 cases with exact sparse
  query correspondence using installed IntelliFold 2.0.4. Both Flash/full
  inference remain untested.

The native Protenix/IntelliFold model geometry features use pseudo-Cβ distances
and N/CA/C frames. Moving distal side-chain atoms by 3 Å changed the input atom
arrays but left those geometry features unchanged in both tested engines.
These are backbone/template guides, not hard catalytic-atom restraints. Only
Boltz is wired into the beta automatic cycling runner. Other engines fail
automatic-cycle preflight explicitly; their template inputs can be exported
for qualification. No Mini/OpenFold/ESMFold2 template capability is implied.
Protein templates do not lock ligand poses. Ligands remain separate predictor
entities and their positions are assessed independently.

Boltz native PDBs retain their generic ligand labels. Separately saved mapped
copies restore CCD labels from the submitted entity map, with native/mapped
hashes and identity receipts; no atom names, elements or coordinates change.
Source-to-conditioning ligand chain/residue maps are also recorded explicitly.

## Saved comparison

The default comparison crosses LigandMPNN and LASErMPNN with fixed sampling,
independent iteration, greedy and beam search. All arms share generated roots.
Each arm receives the same **total** proposal budget per cycle, not a budget
per beam member. Default beam width is four. An extinct iterative lineage
stays extinct; attempted and checked counts are reported separately.

LigandMPNN receives explicit fixed residues and fixed-side-chain context.
LASErMPNN receives `--fix_beta`: catalytic residues have B=1, mutable residues
B=0. Both receive the same ligand heavy-atom coordinates. LASErMPNN hydrogens
are added from each installed CCD graph separately, preserving heavy atoms and
all cofactor/ion instances. Sampling temperatures are recorded in the runner:
0.5 for both designers, with LASErMPNN's separate first-shell temperature 0.7.
No composition constraint or blanket catalytic-cysteine deletion is applied.
Returned sequences must preserve the catalytic identities; failed proposals
are rejected, never repaired by replacing letters afterward.

The beta runner uses the existing resident Boltz predictor and shared managed
job submission, code/runtime retention and execution lock. Directory requests
are made per arm/cycle. Guided predictions supply proposal structures, followed
by separate untemplated predictions of the same sequences for scoring.
Completed design/fold operations are checksummed and reusable on resume.
An interrupted operation without a completion receipt may be rerun. This beta
does not claim the production campaigns' throughput or within-directory
per-item recovery. Runs can be resumed through the shared Jobs interface.

## Geometry objective

The scoring profile is `studio-ame-beta-v2`, **not exact Artios reproduction**:

1. Require complete molecular identities, finite coordinates and nondegenerate
   alignments. Fold gate: root C-alpha RMSD <2 Å and protein pLDDT >80.
2. Rank by `max(original_input_selected_atom_RMSD/2.5, worst_ligand_centroid_shift/3)`, then the sum of
   those normalized terms. Greedy keeps one eligible parent; beam keeps up to
   four distinct sequences. Previously best eligible parents remain available.
3. Add a separately reported source functional-atom guard, default <=1 Å.
   Its tolerance is a beta choice, not a published Artios threshold.

Old prepared bundles must be regenerated: the profile change cannot silently
reuse root-relative search objectives.

Full motif RMSD remains a separate diagnostic and uses a single fit of named motif heavy atoms to the frozen root.
Source recovery uses one fit of the selected functional atoms to the original
fixture. Ligand centroids and named-atom pose RMSDs use one C-alpha fit of the
root pocket (residues with a heavy atom <8 Å from any ligand). Every ligand
must be present; the worst centroid displacement determines the ligand term.
The automatic Boltz path reads per-residue C-alpha pLDDT from its PDB B-factor
field; it records the mean on the 0–100 scale. Strict source atom naming can
penalize chemically equivalent symmetry swaps. Symmetry-aware scoring, clash
gates, detailed catalytic angles and chemistry-aware pose passing are not yet
implemented; pose RMSD is a diagnostic, not an additional passing threshold.
M0630_1j79 has only two selected protein atoms: its sparse residue template is
valid, but a unique selected-atom rigid alignment is underdetermined. Preparation
is allowed; beta inference is rejected until a ligand-anchored scoring definition
is qualified. Source-guide receipts record this diagnostic as null, not zero.

`paper_like_pass` retains the root-relative all-heavy motif metric;
`guarded_pass` adds the original-input guard. These describe computational filters only.
They do not establish catalytic activity or independent validation. No final
different-family assay runner or automatic lab shortlist is claimed. Preserve
the checked candidate identity when performing that separate assessment.

## Motif correspondence and initial backbone selection

Every frozen beta reference records the original source residue, query chain,
1-based query sequence position, amino-acid identity and selected atom names.
All selected atoms are aligned together to the immutable original input.
Per-residue RMSDs use that same global transformation; independently refitting
each residue would hide errors in active-site arrangement. Missing atoms,
identity changes and degenerate alignments fail explicitly.

RFD3's exporter copies fixed motif coordinates into its final PDB. Exported
RMSD alone can therefore be artificially exact. Initial beta roots are ranked
by **candidate selected-atom RMSD before that copy**, then exported RMSD.
`roots.json` and `root_ranking.json` retain both, and every requested root
remains in the comparison. This ranks geometry, not catalytic viability.

New general RFD3 unindexed-motif outputs also preserve original coordinates,
mapping/mask checksums and the pre-copy metric through sequence design and
selection. Validation reports original-input RMSD separately from recovery of
the generated backbone. For new rows the motif threshold applies to original
recovery too. Legacy rows without original-reference provenance report that
metric as unavailable; they cannot be reconstructed honestly from a generated
backbone. Studio results expose both metrics with their distinct references.

The CPU command `score-input-motif --reference reference.json --structure
prediction.cif --output report.json` scores a mapped beta reference against
any compatible prediction, including an apo structure. It requires neither
ligand output nor predictor confidence. Full beta ranking still requires its
ligand and confidence checks.

## Chemistry audit

The local installed Boltz CCD cache exactly matches the **heavy-atom sets of
38/41** released cases. Three require an explicit chemical variant:

| Case | Component | Full CCD atoms absent from released fixture |
|---|---|---|
| M0024_1nzy | BCA | O7A, O8A, O9A, P3D |
| M0054_1qfe | DHS | N |
| M0731_1mt5 | MAY | F |

Do not silently complete these molecules, delete atoms from the predictor's
graph, or guess protonation. The beta rejects them for automatic cycles.
Matching atom sets alone do not prove that the chosen CCD protonation/tautomer
is the best experimental state. The matching count happens to be 38; **this
does not establish that these are the three Artios exclusions**.

The complete audit, including CCD hashes, bonds, formal charges and
stereochemistry, is in the retained local audit described in [Lab Book 0489](../lab_book/0489-implement-atomic-motif-beta.md).
All 41 file-only bundles are prepared in the adjacent `prepared/` directory.

## Developer and qualification interface

`pipeline/scripts/motif_beta_cli.py` exposes CPU-only `prepare`, `freeze-root`,
`templates`, `source-guide`, `designers`, `score-input-motif`, `score`, `select`
and `chemistry-audit` operations.
`_managed-run` is the private bridge-owned inference entry point; do not launch
it outside the broker. Native submissions use workflow `motif_beta` and a
strict `motif_beta_request.json`; no executable or shell-command field exists.

`source-guide --case CASE --mapping map.json --sequence SEQUENCE --output guide.json`
uses the released full residues without generating a scaffold. The mapping is
an exact JSON object such as `{"A39": 2, "A219": 6, "A376": 10, "A399": 14}`
for M0040_13pk: values are 1-based query positions and the query must preserve
the residue identities there. Add `--structure native.cif` to extract from a
native protein instead. Missing backbone/catalytic atoms, ambiguous selected
conformers and identity mismatches fail explicitly. Other protein residues are
excluded. Pass the resulting guide to `templates --reference guide.json
--sequence SEQUENCE --engine ENGINE --output DIRECTORY`. This prepares inputs;
it does not design a sequence, infer a fold or relax disconnected residues.

Native-protein import and arbitrary query placement are currently CPU workbench
operations; the GUI's original-residue option uses the released benchmark files
and RFD3's placement map. Protenix/IntelliFold native CPU features are checked; model inference and
automatic cycles remain unqualified. Input audits and the full native example
are in the retained local audit described in [entry 0490](../lab_book/0490-support-original-motif-residue-templates.md).
Native feature and correspondence checks are recorded in
[entry 0491](../lab_book/0491-preserve-original-motif-correspondence.md).

The tests execute all case preparation, rigid-transform invariance, per-ligand
displacement/missing-atom failures, centroid-preserving rotations, sequence
locks, duplicate suppression, equal policy budgets with fake model outputs,
operation replay/tampering, real Boltz sparse-template parsing and real RDKit
multi-ligand protonation. These tests load no model weights.

Before a scientific campaign: qualify memory profiles through the repository's
Validation process, run one root through both real sequence designers and all
requested prediction stages, inspect native template features, and independently
check a frozen shortlist. Extend to other engines only after equivalent tests.

## Public CLI and MCP (bridge 45)

Read-only discovery uses `motif_beta_catalog` and `workflow_guide` with
`workflow: "motif_beta"`. Plan with `motif_beta_plan`; the executable recipe
route is also `motif_beta`. Both use the existing desktop adapter, immutable
provenance, memory policy and shared execution lock. Planning does not launch
inference. Read the returned budget before `job_start` with its exact ID/digest.
Existing output names are rejected; use the original job's resume action.

The CLI equivalents are:

```bash
python3 "$NANOHUNTER_ROOT/mcp/studioctl.py" motif-catalog
python3 "$NANOHUNTER_ROOT/mcp/studioctl.py" guide motif_beta
python3 "$NANOHUNTER_ROOT/mcp/studioctl.py" evidence
python3 "$NANOHUNTER_ROOT/mcp/studioctl.py" plan-motif-beta request.json
```

A file-only preparation request is:

```json
{"project":"my-project","run_name":"motif-preparation","request":{"case_id":"M0040_13pk","stage":"prepare"}}
```

Stages `backbones` and `cycles` require their installed engines and existing
preflight checks. The default request compares multiple designer/policy arms;
inspect `prediction_budget` rather than assuming one root means one prediction.
No extra shell or direct GPU execution path is introduced by these entry points.
