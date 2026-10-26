# RFD4 in Studio

Choose **Design → a recommended workflow**, or select an intention under **Build a custom workflow** and choose RFD4. The detailed form also remains available under **RFdiffusion → RFD4**. The development integration uses a verified local
portable runtime and separately pinned weights. Public runtime distribution is
pending; see Lab Book 0559 for the acceptance status of this build.

| Task | Input and behavior |
| --- | --- |
| Monomer | Requested length; joint sequence/structure generation |
| Protein binder | Target structure and source chain; Studio derives the contig; optional source-numbered hotspots |
| Small-molecule binder | SMILES with explicit stereochemistry/charge, or a chemical component with explicit bonds; checked conformer preparation preserves chemistry |
| Nanobody | Target structure plus the audited 7XL0 framework, or custom annotated input / retained segments |
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
redesigns only the specified nanobody CDRs. Full, Fast or Boltz refolds complete
sequences. Every proposal and its exact parent are retained. Beam selection ranks
the current family generation without retaining a parent by default. Imported
starting structures permit these searches on existing backbones too.

**Native rollout search** is a separate option. It invokes the pinned upstream
RFD4 beam implementation and scores completed rollouts at the selected checkpoints.
Protein oracles use interface ipSAE; ligand oracles use Boltz Pbind plus ligand
pLDDT/100. Ligand graph, charge and stereochemistry must match the supplied scoring
SMILES. Rollout feedback is optimization evidence, not an independent binding check.

Plans freeze inputs, model identities, code, settings and prediction budgets.
All inference uses Studio's broker and shared execution lock. Completion receipts
are checked before reuse; interrupted attempts are retained. Runs above ten
families complete one end-to-end family before proceeding. Memory admission is
not yet calibrated for RFD4, so running it requires the visible experimental
memory override. Optional Metal kernels must match reference output exactly on
the first input before the campaign proceeds.

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
and four surviving parents. Nanobody redesign is restricted to CDR1/2/3 on the
7XL0 framework. Easy small-molecule workflows assess the native RFD4 sequence with
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
chosen framework uses its bundled alignment. Missing required assets fail before
launch; models and alignment policies are never silently substituted.

The custom builder offers only methods appropriate for the selected intention.
Use **Save workflow as button…** to save its settings and input references. Saved
buttons reopen editable settings and never launch compute immediately. Existing
workspaces remain readable; workflow snapshots have a versioned schema.


### Sequence targets and assemblies

Recommended protein and nanobody buttons accept a structure or complete sequences
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
| Nanobody | RFD4 with the audited framework; X-token hallucination, including ESMFold2 Full CDR-only starts |
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
