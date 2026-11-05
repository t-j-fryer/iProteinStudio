# RFD4 in Studio

Choose **Design → a recommended workflow**, or select an intention under **Build a custom workflow** and choose RFD4. The shared **Backbone design** form has a **Generate with** dropdown for RFD4 or RFdiffusion3; its fields change with the selected generator. Studio 0.2.27 uses the published [RFD4 portable runtime](https://github.com/t-j-fryer/iProteinStudio/releases/tag/runtimes-2026.10.26-1) and separately pinned model downloads. See [integration acceptance](../lab_book/0559-integrate-rfd4-and-design-search.md) and [release qualification](../lab_book/0579-qualify-and-release-studio-027.md) for tested routes and limits.

| Task | Input and behavior |
| --- | --- |
| Monomer | Requested length; joint sequence/structure generation |
| Protein binder | Target structure and source chain; Studio derives the contig; optional source-numbered hotspots |
| Small-molecule binder | SMILES with explicit stereochemistry/charge, or a chemical component with explicit bonds; checked conformer preparation preserves chemistry |
| Nanobody | Target structure plus any of the eight bundled frameworks, or custom annotated input / retained segments |
| Motif | Native annotated CIF, or explicit retained residues and generated segments |
| Partial diffusion | Complete source coordinates and partial trajectory fraction |
| Inverse folding | Source coordinates; native inverse-folding operation with a terminal C-alpha preservation audit |
| Annotated input | Native CIF conditions are retained as supplied |

The advanced condition editor forwards native RFD4 selections and values to the
pinned upstream authoring implementation. An annotated CIF is the route for
native conditions beyond that editor. Preflight runs authoring and feature
preparation in separate CPU processes, and reports invalid conditions before
loading the model. Missing files, unsupported requests and failed audits stop
the run. The released sampling schedule is preserved.

Protein, nanobody and small-molecule inputs can use fixed-backbone sampling, iterative refinement,
greedy search or beam search. SolubleMPNN is the protein-binder default; AbMPNN
redesigns only the specified nanobody CDRs. The predictor menu groups ESMFold2
Full/Fast/600M, Boltz-2, IntelliFold Flash/Full, Protenix v2/Mini/Constraint and
OpenFold-3 by family. These reuse the existing resident adapters and require their
own installed checkpoint; an absent engine is never substituted. Each proposal
receives one prediction sample at the selected engine’s Studio profile. Every proposal and its exact parent are retained. Beam selection ranks
the current family generation without retaining a parent by default. Imported
starting structures permit these searches on existing backbones too.

**Native rollout search** is a separate option. It invokes the pinned upstream
RFD4 beam implementation and scores completed rollouts at the selected checkpoints.
Protein oracles default to interface ipSAE; ligand oracles default to Boltz Pbind plus ligand
pLDDT/100. Ligand graph, charge and stereochemistry must match the supplied scoring
SMILES. Rollout feedback is optimization evidence, not an independent binding check.

Plans freeze inputs, model identities, code, settings and prediction budgets.
All inference uses Studio's broker and shared execution lock. Completion receipts
are checked before reuse; interrupted attempts are retained. Runs above ten
families complete one end-to-end family before proceeding. Memory admission is
not yet calibrated for RFD4, so running it requires the explicit
memory override. Optional Metal kernels generate only the requested designs.
Exact-reference comparisons belong to developer validation; normal jobs do not
duplicate generation for qualification. Finite-output, target-sequence, sampling
completion and saved-artifact integrity checks remain enabled.

This integration does not promote retrospective adaptive-depth allocation,
multi-cycle inverse-fold/refold experiments, or unqualified conditioning profiles
to defaults. Those remain research work. Ligand sequence proposals reuse NISE's LASErMPNN sampler and Boltz oracle, with P(bind) + ligand pLDDT/100 selection. NISE remains available as its own method. RFdiffusion3 DNA/RNA generation remains out of scope.

Full CDR-only X-token starts are in **Protein Hunter → Nanobody**, not the RFD4
generator. See [ESMFold2](ESMFOLD2.md). Whole-chain ESMFold2 X-token generation is
not enabled.

## Recommended and saved workflows

Easy minibinder/nanobody workflows generate native RFD4 sequences and assess them
with ESMFold2 Full. Hard workflows start with RFD4, then use SolubleMPNN or AbMPNN
proposals and Full refolding for up to seven cycles, four proposals per parent,
and four surviving parents. Recommended nanobody buttons default to CDR1/2/3 on
the 7XL0 framework; the detailed custom form offers all eight catalogue frameworks. Easy small-molecule workflows assess the native RFD4 sequence with
Boltz; hard workflows use seven-cycle LASErMPNN beams and the same combined score.
These are the user-selected workflow definitions, not new efficacy claims.

Specify active minutes. Queue time and between-session downtime are excluded;
model loading and MSA work count. A running atomic operation finishes even if it
crosses the deadline. Every completed candidate is retained, including candidates
from an unfinished family. Very short budgets may end during setup without a
candidate. Timed runs currently process one family at a time; their throughput
has not been benchmarked against batch campaigns. The 10,000-family ceiling is a
secondary bound, not a requested cohort before the time limit.

Automatic target alignments reuse Studio's cache or contact the configured MSA
server; explicit alignments and single-sequence policy remain selectable. The
chosen framework uses its bundled alignment, or the shared cache/server resolver
when a catalogue framework has no bundled alignment. Missing required assets fail before
launch; models and alignment policies are never silently substituted.

The custom builder offers only methods appropriate for the selected intention.
Use **Save workflow as button…** to save its settings and input references. Saved
buttons reopen editable settings and never launch compute immediately. Existing
workspaces remain readable; workflow snapshots have a versioned schema.


### Sequence targets and assemblies

Both the recommended buttons and the detailed RFD4 form accept a structure or complete protein sequences
separated with `:`. ESMFold2 Full prepares the entire assembly through a managed
`target_prepare` job, with chains B, C, D onward and per-sequence automatic MSAs.
The shared resolver reuses audited alignments or requests missing ones through
Boltz; it does not fall back silently to single-sequence prediction. The design
starts only after preparation succeeds. Preparation time is separate from the
active design-time budget. If the app closes during preparation, the managed job
remains in Jobs; its completed structure can be selected as the design input. The
form reuses target predictions already recorded in the target cache.

RFD4 retains all supplied protein chains unless an explicit source-chain selection
is entered. Use chain-qualified source hotspots (`B32 C55`, or `B:32 C:55`) for
multiple chains. Bare numbers remain valid for a single-chain target. The source
chain-to-output mapping and each sequence are frozen in `target_identity.json`.
The target assembly is held as one coordinate group during protein authoring;
separate chains, sequences and per-chain MSAs are retained throughout refinement.
Multichain scoring keeps the existing conservative minimum directional ipSAE
across all protein pairs, including target–target pairs. This is optimization
feedback, not proof of a binding interface.

The pinned upstream contig inserter can leave stale molecule instance IDs after
inserting a generated chain before multiple retained chains. Studio re-runs native
AtomWorks ID/entity and instance annotation at that boundary, before native
conditions and strict validation. It does not change bonds or coordinates.
Protein PDB inputs are converted with the native parser and CIF writer before
condition authoring; ligand inputs still need explicit chemical connectivity.

### Custom workflow capabilities

| Intention | Available starting methods |
| --- | --- |
| Monomer | RFD4; native unconditional RFD3 followed by sequence refinement; X-token hallucination with a compatible predictor |
| Minibinder | RFD4; RFD3; X-token hallucination |
| Nanobody | RFD4 with a catalogue framework; X-token hallucination, including ESMFold2 Full CDR-only starts |
| Small-molecule binder | RFD4; RFD3; X-token hallucination; NISE |
| Motif scaffolding | RFD4/RFD3 structural conditioning; Boltz sequence-motif X-token starts; the existing atomic-motif beta |
| Optimize a structure | RFD4 partial diffusion or inverse folding; RFD3 partial diffusion; X-token partial sequence redesign |

The custom chooser labels the original Protein Hunter route **X-token
Hallucination**. RFD3 monomer generation uses its native unconditional length
specification, then the existing SolubleMPNN/refiner handoff. Monomer forms omit
target inputs and interface hit thresholds. Whole-chain ESMFold2 X-token starts
remain unsupported; Full can refine complete sequences or initialize supported
fixed-framework CDR requests. RFD3 fixed-framework nanobody generation was tried unsuccessfully and is
excluded from Studio; it is not an outstanding integration task.

General coordinate-template-guided X-token motif generation is not implemented.
The existing atomic-motif beta uses benchmark motifs, RFD3 starts and mapped
Boltz template guidance; it is accessible directly from the motif chooser.
Protenix and IntelliFold sparse motif template features have CPU qualification
only, not qualified model inference or automatic cycling. Ordinary target
templates do not template the designed chain and are not a substitute for this.

Implementation and bounded technical checks: [Lab Book 0574](../lab_book/0574-sequence-targets-and-workflow-capabilities.md).

## macOS support

Studio currently gates RFD4 at macOS 26.2. The shipped runtime manifest and
its native binaries declare 14.0; a 26.2 dependency was not found in the binary
audit. This is a conservative support gate, not a demonstrated RFD4 requirement.
Older-system inference remains untested. See [the dependency audit](MACOS_SUPPORT.md).


## Detailed configuration

- **Target structure** is the protein to bind, not the nanobody framework. Multiple
  protein target chains retain their assembly geometry. The detailed form can
  predict a target once from sequences separated with `:` through the existing
  managed target-preparation job. Its time is separate from the design budget.
- **Nanobody framework** loads its own CDR1/2/3 boundaries from the catalogue.
  Positions are one-based and inclusive in the nanobody sequence. They determine
  which positions AbMPNN can change and which positions are masked in its MSA.
  An advanced override is explicit and can be reset to the catalogue boundaries.
  The 3EAK boundaries were transferred by sequence alignment, not independently
  numbered. A custom annotated input needs explicit boundaries and an MSA policy.
- **Sequence sampling temperature** controls sampling diversity. **Excluded amino
  acids** uses one-letter codes: `C` excludes cysteine; empty allows all residues.
  **Generation seed** sets reproducible per-family seeds. Designed chain A and
  target chains B onward are output chain roles; epitope fields use input chains.
- **Length range** distributes starts evenly over the requested integer lengths.
  When starts are fewer than lengths, they span the interval; a single start uses
  its midpoint. Custom counts must sum to the family budget. Starts are interleaved
  by length, including timed runs. Each distinct length gets a separately authored,
  audited native input in the frozen plan. Imported structures and native
  during-diffusion search retain their own fixed lengths.
- **Hit filters** flag candidates meeting all selected ipSAE(min), iPTM and/or mean
  complex pLDDT cutoffs. Cutoffs use the 0–1 scale; missing metrics fail that filter.
  Verdicts, failed criteria and cutoffs are saved beside the candidate. The Hits
  view reads those verdicts. Every proposal is retained and parent selection is
  unchanged. These are search-score gates, not independent validation.
- **Optimized GPU operations** are custom Metal pair operations. Reference comparison
  is performed in developer validation, not automatically within design jobs.
  This is not an accuracy option or a guarantee of a speedup on every input. New requests use this option by default; turn it off to use standard operations.

### Mixed protein–ligand targets

This means a protein binder being designed against a protein that already carries
a small molecule, such as an enzyme with a bound cofactor. The complete assembly
contains the new binder, the target protein and the ligand. It is distinct from
designing a protein that binds a free small molecule.

For protein/nanobody targets, supply a PDB or CIF containing the target protein
and its noncovalently bound small molecules. Studio retains every non-water
ligand instance, including when protein target chains are selected explicitly.
Supply a file containing only the intended ligand instances. It records an exact
chemical graph, formal charge, source-coordinate stereochemistry and source atom
names in `target_ligands.json`; it does not standardize or change protonation.
Missing connectivity, incomplete coordinates, covalent links to polymers and
nucleic-acid context fail before submission.

RFD4 conditions on the protein–ligand assembly. Every subsequent compatible
prediction contains the target proteins, designed chain and the same ligands.
SolubleMPNN/ProteinMPNN and AbMPNN retain their protein-backbone roles: the ligand
is retained in the parent assembly but these inverse folders are not claimed to
score ligand interactions. Prediction and complete-assembly checks provide that
structural context during search. This is separate from the dedicated free-ligand
binder workflow, which uses LASErMPNN and the ligand affinity objective.

Each prediction keeps its original output plus a complete `assembly.cif`, an
explicit native-to-source atom map and `assembly_audit.json`. Missing atoms,
changed elements or chain identities stop the run. A separate geometry verdict
reports target-aligned ligand RMSD and checks source stereochemistry, gross bond-length errors and severe protein–ligand
clashes; a failed verdict cannot be reported as a passing hit. Protein ipSAE is
calculated with the predictor's full token layout and excludes ligand tokens
from protein-interface pairs. It is not a ligand affinity score. All candidates
remain saved and default search ranking remains protein ipSAE; geometry is an explicit
hit gate. Imported mixed assemblies require the RFD4 CPU preparation component
and chemically defined CIFs (or complete CCD-defined ligands in PDB files).

Bounded end-to-end checks cover ten predictor profiles, eight catalogue frameworks, two protein lengths, and twelve mixed-target routes with two predictions each. One native nanobody start was reused from its audited generation after a serialization fix. These establish software integration, not binding efficacy or every possible framework/engine combination. See [qualification and limits](../lab_book/0684-preserve-mixed-target-context.md).

### Shared backbone configuration (local candidate)

The custom builder now has one **Backbone generation** starting method and an
explicit **Backbone generator** choice. RFD3 and RFD4 retain their native
execution and conditioning contracts. RFD3 fixed-framework nanobodies remain
unavailable. The following additions are prepared locally; see Lab Book 0719
for verification and remaining release qualification.

For nanobodies, enable **Use multiple catalogue frameworks**, select the desired
frameworks and set positive relative weights. A weight of two receives twice the
starting-family allocation of a weight of one over a complete allocation period.
Smooth weighted round robin interleaves starts; short runs may stop before the
requested proportions are realized. Preflight rejects a finite family budget
that never reaches one of the selected frameworks. Each family has its own
catalogue structure, CDR boundaries and alignment. Custom annotated frameworks
remain a separate single-framework route.

**Target sequence alignment (MSA)** means evolutionarily related sequences of
the protein being bound. **Framework sequence alignment (MSA)** supplies related
framework sequences for nanobody prediction, with redesigned CDR positions
masked. These are not structural alignments. Automatic uses the existing
cache/server resolver; an imported A3M or explicit single-sequence mode remains
available. Multiple frameworks require automatic per-framework alignments or
single-sequence mode. Missing requested assets fail before inference.

**Select candidates by** controls search ranking, separately from hit
filters. Protein candidates can maximize ipSAE(min), iPTM, pTM or mean complex
pLDDT. Ligand candidates can maximize Boltz P(bind), ligand pLDDT, their original
combined score, iPTM or mean complex pLDDT. ESMFold2 Full/Fast/600M ligand routes
support confidence objectives, using the existing complete-sequence prediction
and ligand atom-map adapter; binding probability requires Boltz. Requested
metrics that are absent, nonfinite or outside their declared scale stop selection.
Raw metrics, objective identity and every proposal remain recorded. Scores from
different engines are not assumed to be calibrated comparably. Native diffusion
rollout search uses the selected objective through upstream reward aggregation;
its ligand oracle remains Boltz.

**Target binding site** is visible in the protein and nanobody forms. Enter
input-chain residue IDs, or use **Select residues on target structure…** and
click them in the viewer. The target can be imported or prepared from sequence.
Hotspots guide backbone generation; they do not redefine the ranking objective.

RFD4 SMILES input now reuses the molecule analysis panel: structure drawing,
conjugation/linker picks, optional PDB search, chemical-state notes and selected
conformer shares. The selected SDF conformers are copied, hashed, mapped to the
exact SMILES graph/charge/stereochemistry and authored into separate native
inputs. The analysis reports chemistry issues; it does not silently select a
different tautomer or protonation state. **Inspect atoms** and **Suggest atom
conditions** expose burial, exposure, contacts and hydrogen-bond roles. A recorded
mapping translates the viewer's canonical atom names to RFD4's input names.
RFD4 uses its native RASA and hydrogen-bond enums; exposed atoms cannot also
receive pocket-pulling conditions. External annotated CIFs continue to use their
own native conditions. Multi-framework and conformer allocation applies to
ordinary generation and sequence search, not native rollout search.

### Molecule preparation controls

The generator is chosen inside one scrolling design form, without separate
RFD3/RFD4 tabs. SMILES, linker endpoints, conformer choices and atom conditions
carry across a switch between de novo small-molecule generators. Each generator
keeps its own sampling and scoring controls.

- **Analyse this molecule** checks chemistry, generates and groups candidate 3D
  conformers, and optionally searches the PDB. It does not start protein design
  or predict binding. Observed PDB shapes are not estimates of solution populations.
- **Inspect atoms for binding-site conditions** resolves atom identities and
  chemical roles for the condition checklist; it does not select restraints.
- **Preview suggested atom conditions** proposes non-polar burial, ligand
  donor/acceptor roles and exposure of an analysed linker. Applying the reviewed
  proposal replaces the current selections. Hotspots are chosen by the user.
- **Clear all atom conditions** clears the saved selections and drawing overlays.
  Coloured rings and B/E/D/A/H labels identify buried, exposed, ligand donor,
  ligand acceptor and hotspot atoms. Split rings preserve multiple roles.

Tautomer notes are under an optional disclosure. They describe possible changes
in hydrogen placement/bond order, not 3D conformers or predicted populations at
a given pH. Studio uses the supplied SMILES chemical state. The RFD4 paper's
Section S7.1.3 describes donor/acceptor assignment on a pH 7.4-protonated copy
for its interaction-search experiment; that is distinct from requiring routine
tautomer enumeration. See [the paper](https://rfd4-proteina.org/assets/paper/RFD4-Proteina.pdf)
and [upstream interaction-metric settings](https://github.com/RosettaCommons/RFD4-Proteina/blob/main/configs/metrics/inline_metrics/ipa_metrics.yaml),
where the inspected version has `tautomerise: false`.

### Editable family budgets and Metal evidence

**Families** accepts a typed integer from 1 to 10,000. Empty, non-integer and
out-of-range edits block Start rather than silently submitting the prior budget.

**Optimized GPU operations** combines custom triangle and pair operations while
preserving model weights and sampling steps. Recorded results on an Apple M4 Max
(40 GPU cores, 64 GB, macOS 26.6.1, BF16 MPS, Torch 2.14.1):

| Comparison | Observed reduction in generation time | Scope |
| --- | --- | --- |
| Standard → triangle operations | 5.48–12.93% mean reductions in seven settings with both paired measurements faster | Warmed unconditional 64/128 residues, batches 1/2/4/8; 64-residue batch 8 was inconclusive |
| Triangle → added pair operations | 8.17–12.21% | Separate warmed 64/128-residue batch 1/4 tests; four measurements per arm/settings |
| Standard → triangle + pair, target-conditioned first call | No saving: 41.498279 → 41.673889 s | One 216-token SUMO–binder call per arm, including first-use effects |

These numbers are copied from measured Lab Books 0502, 0506 and 0514, not new
measurements. The two warmed comparisons cannot be multiplied into a claimed
total speedup. They exclude model loading, preparation, export and downstream
prediction. All compared saved tensor fields and sequences matched exactly;
coordinate differences were zero. That establishes output agreement for the
tested cases, not biological accuracy or equal binding yield across targets.
Normal jobs no longer repeat designs against the reference. Developer validation
retains matched standard/optimized comparisons; production retains output-integrity
and resume checks. Existing saved plans keep their frozen behavior. The optimized
option is on by default for new requests; explicit saved choices are preserved.

### Guided RFD4 motif authoring

Choose Motif scaffolding and supply a PDB/CIF, or use Predict from sequence to
prepare a saved structure through the normal queue. Choose motif residues in the
viewer/list and their exact finite coordinate atoms; amber spheres mark those
atoms. Input labels are the pinned native parser’s chain IDs and residue numbers.
The inspected source hash is retained and checked before authoring.

Geometry maps to native `C_CRD` (absolute) or `C_CRDGRP` (one relative group).
Sequence identity maps to `C_SEQ`; sidechain coordinate selection requires fixed
identity. Free sequence placement uses `C_IDX=false`, grouping either contiguous
segments or individual residues. Prefix/linker/suffix minimum/maximum lengths
compile to native expandable contig segments; 0–0 omits a segment. The guided
form scaffolds one protein chain. Multi-chain/non-protein motifs and other native
conditions remain available through annotated CIFs and the explicit condition editor.

CLI/MCP use the same typed `motif` object. Example request (ordinary 2LZM chain A):

```json
{"task":"motif","source":"2LZM.pdb","motif":{"residues":[{"chain":"A","residue":10,"atoms":["N","CA","C","O"]}],"coordinate_mode":"absolute","fix_sequence":true,"unindexed":false,"group_segments":true,"prefix":[30,35],"linker":[5,10],"suffix":[30,35]}}
```

`rfd4_cli.py inspect-motif --root ROOT --config source.json --output INSPECTION`
reads `{ "source": "2LZM.pdb" }` and saves the native inventory, normalized viewer
CIF and source fingerprint. Sequence inputs use `target_prepare_plan` first;
then pass its completed structure into the motif plan. Annotated CIFs retain
their existing settings; typed motifs cannot silently override them.

Native syntax: [upstream input preparation](https://rfd4-proteina.org/latest/how-to/input_prep/yaml-json.html).

For indexed motifs, final scaffold length includes the selected motif residues
plus the generated segments. Unindexed motifs occupy generated positions: final
length is the sum of the generated segments, without adding motif residues again.
Lengths sample from each design seed. Coordinate conditioning is a model input,
not an exact output guarantee; assess generated motif RMSD and refolding before
interpreting a design as successful. Upstream exposes motif-adherence metrics:
https://rfd4-proteina.org/latest/reference/metrics.html


## Partner-aware motifs and final prediction (beta)

Select the motif-bearing protein residues/atoms, then select retained protein
chains and ligand instances in the motif editor. Partners must share the input
complex's coordinate frame. Native condition-spec authoring retains their sequence,
chemistry and geometry in the same coordinate group as the motif. Unselected
chains/ligands are omitted. Protein scaffolding remains on one designed chain.
Noncovalent ligand instances use explicit native chemistry and atom maps; covalent
attachments and nucleic acids are not supported by this guided route.

For sequence input, enter the motif-bearing chain and provided partner sequences
as separate chains and predict the complete complex first. The resulting proposed
complex becomes the reference. Studio does not silently place a separately
predicted target beside an experimental motif or claim a known binding pose.

Final prediction can assess the scaffold alone (apo), with retained partners
(holo), or both. Each is an untemplated prediction of the generated sequence.
The designed chain uses an explicit empty MSA; retained natural protein partners
use the selected alignment policy. Boltz and ESMFold2 support ligand holo checks;
protein-only checks expose the existing protein predictors. This is final
assessment, not motif beam reward or sequence search.

Hit gates compare exactly the selected named atoms to the input motif using the
native generator's insertion map, including unindexed motifs. Shape RMSD fits
those motif atoms once. Optional holo placement RMSD fits retained partner Cα
atoms and ligand heavy atoms and measures the motif without a second fit.
Both use one proper rigid transformation; no symmetry reassignment or nearest-atom
matching is performed. The selected fit atoms must be noncollinear. All selected
modes must pass all requested cutoffs; missing/ambiguous atoms fail explicitly.
No cutoff means no hit classification. The editable 2 Å initial value is a UI
starting point, not a validated efficacy threshold. Ligand assembly integrity is
also required when calling holo hits. Apo/holo metrics and structures remain
separate in results. Low RMSD does not establish binding, stability or activity.

Upstream semantics: https://rfd4-proteina.org/latest/concepts/conditioning.html;
metric distinctions: https://rfd4-proteina.org/latest/reference/metrics.html.
