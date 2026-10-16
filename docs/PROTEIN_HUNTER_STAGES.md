# Protein Hunter: starting backbones and refinement

Choose a workflow from the tabs at the top of Protein Hunter, using the same
segmented layout as RFdiffusion3: **De novo design**, **Partial noising**, or
**Motif scaffolding**. Partial noising exposes a source binder, the sequence regions
to redesign and their initial X-token percentage. Motif scaffolding exposes the
source sequence, motif ranges and minimum sequence gaps; it requires Boltz.
These two modes preserve sequence constraints while coordinates can move.
Nanobody CDR design stays under De novo design; the region modes accept
mini-binders or peptides. Source sequence and region settings survive switching
tabs and reopening saved workspaces.

Protein Hunter can use one method to make its starting backbones and another to
refine their sequences. Existing workspaces keep the original single-engine
workflow unless you change **Starting backbones · cycle 00**.

| Starting method | Cycle 00 | Cycles 01 onward |
|---|---|---|
| Same engine as refinement | Original X-token hallucination | MPNN followed by the selected engine |
| Separate hallucination engine | X-token hallucination with your starting engine | MPNN followed by each selected refinement engine |
| RFdiffusion3 | De novo backbone generation around the target | MPNN followed by each selected refinement engine |

A trajectory gets one starting structure. With 10 trajectories and 5 refinement
cycles, each engine campaign produces 10 starts and 50 optimized structures.
Cycle 00 is a starting backbone, **not a designed sequence or a hit**. Selecting
multiple refinement engines creates separate campaigns, each with its own
starting generation and exact trajectory budget. This is not a paired-backbone
benchmark; use saved matched starts for such a comparison.

## Choosing the stages

For example, select **Separate hallucination engine → Boltz-2**, then select
**ESMFold2 Fast MLX** in the refinement checklist. Boltz makes the initial fold;
MPNN designs a complete sequence on that structure; ESMFold2 folds that sequence.
The next MPNN step uses that new predicted structure, as in the original loop.
The starting engine is released before the refinement model loads. Resident
refinement models remain loaded while later cycles' sequences are prepared.

ESMFold2 cannot be selected for X-token initialization. Fast is sequence-only and
uses no target MSA. Full can use the target MSA and performs more internal
refinement. Both reuse the existing portable ESMFold2 runtime and shared ESMC
weights. Their speed/accuracy differences depend on the target and settings;
see [measured ESMFold2 evidence and upstream credits](ESMFOLD2.md). Mixing engines
does not guarantee better binders, and scores from different engines are not
calibrated against each other. Independent final checks remain advisable.

**Guidance has stage scope.** The starting engine applies its supported pocket,
hotspot or target-template guidance. Later cycles apply only guidance supported
by the chosen refinement engine. ESMFold2 refinement is unrestrained: no pocket
restraints, target templates or Boltz affinity head. Original and derived inputs
are saved separately so this distinction can be inspected.

## Targeting a protein epitope

Enter hotspots once under the protein target, or select them in Target Prep.
Numbers are **1-based positions in the supplied target sequence**, not arbitrary
PDB residue numbers. Bare numbers refer to target chain B; use `B32 C55` for
multiple target chains. RFdiffusion3 maps these positions to the matching source
structure's chain IDs and residue numbers, including numbering gaps.

| Engine | How the shared hotspots guide a design |
|---|---|
| Boltz 2 | 6 Å pocket restraints with steering potentials; nanobody designs also steer the CDR3 centre |
| Protenix Constraint v0.5 | The trained 8 Å token-centre pocket prior |
| RFdiffusion3 | Hotspot conditioning during backbone generation |
| Other refinement engines | No epitope restraint; the predicted interface may move to another site |

**Keep epitope guidance during refinement** is on by default. With RFdiffusion3
starts, select Boltz 2 or Protenix Constraint to keep targeting the same site in
cycles 01 onward. Switching the control off keeps cycle-00 targeting but removes
the shared epitope restraints during subsequent refinement. Other refiners remain
selectable, with an explicit explanation that they cannot apply the hotspots.
The initial engine can also be unguided while the refinement engine is guided.
The screen shows each stage's effective policy, including mixed engine checklists.

These mechanisms are not equivalent distance filters. In particular, the
Protenix cutoff measures token centres, not nearest heavy atoms. Its initial
paired validation showed weak pocket steering; do not interpret the prior as
proof of epitope binding. Independent structure checks remain unrestrained.

CLI and MCP `iterative_plan.arguments` expose the same switch:
`--refinement-epitope-guidance auto|off`. Omission preserves historical guided
refinement with supported engines. Hotspots remain in the shared input YAML's
`nanohunter.target_epitope_residues` list; CLI also accepts
`--target-epitope-residues B32,B55`. The CLI override reaches both Boltz and
Protenix Constraint. Separate-stage runs save the original input and derived
stage templates, and record the refinement choice in the handoff receipt.
Resume uses the recorded command and inputs; changing guidance is a new run.

## RFdiffusion3 starts

RFdiffusion3 is available for de novo minibinders/peptides, not fixed-framework
nanobodies. For protein targets, use **Predict target structure…** to select a
prediction engine (including ESMFold2 Fast/Full), or supply your own PDB/CIF.
The predicted structure is automatically selected for cycle 00; choosing
hotspots is optional. **Use structure** closes Target Prep without adding
hotspots. Existing matching predictions can be reused. RFdiffusion3's own tab
offers the same action and automatically reads the resulting chains/residues.
The target-only prediction uses Studio's normal queue, separately from the
design campaign. Start the design after the target is ready. Choose **Re-predict…**
to change engines without deleting the previous prediction.

Both workflows copy the selected target into the design run before queueing.
For a Studio target prediction, its saved prediction configuration and checksum
receipt are also copied; deleting or replacing the library prediction does not
change a queued design. The selected structure must contain complete chains matching
the target sequences. Studio selects exact matching chains and reserves chain A
for the binder. Ambiguous or incomplete matches fail before GPU generation.
Target sequence positions are translated to structure residue numbers before
applying hotspots. Without hotspots, the established surface-scan placement is
used; the protein's centre of mass is not substituted.

Generation uses the established RFdiffusion3 profile: 200 steps, 2 recycles,
BF16, batch size 4, 2 queues per length bin and the managed EMA weights/patches.
The requested count is spread across up to 20 lengths within the chosen range.
These are generation settings, separate from prediction settings. X-token
percentage and sequence helix-kill do not control RFdiffusion3.

For a SMILES ligand, atom identities are translated between the existing Boltz
atom selector and RFdiffusion3 input-order names, including the affinity
standardization setting. The managed Boltz environment is used for this CPU
mapping even when refinement uses ESMFold2; its model is not loaded for mapping.
The existing NISE tab remains the workflow with repeated ligand-specific
exposure/exit filtering and sequence-scorer optimization.

## Progress, stopping and resuming

The log identifies initialization, handoff and refinement. Generated structures
are browsable during initialization; normal run/cycle grouping takes over after
the cohort handoff. Each cycle records its actual structure engine. RFdiffusion3
starts have no invented confidence or per-backbone prediction time.

The entire campaign occupies one Studio job and one shared execution lease.
Stopping stops the owning process tree. On resume, saved starting structures and
inputs are verified against their checksum receipt before reuse. Changed seeds,
targets or stage settings require a new run. Partial outputs never satisfy the
handoff: counts, readable finite coordinates and chain lengths must pass first.
The normal later-cycle checkpoints then resume through the existing Hunter loop.

## CLI and MCP

`--predictor` chooses the refinement engine. Add either:

```text
--initialization-method hallucination --initialization-predictor boltz
```

or:

```text
--initialization-method rfd3 --initialization-target /path/to/target.pdb
```

`--initialization-model v2-flash|v2` distinguishes the initial IntelliFold
checkpoint. These options require explicit `--template-yaml`, `--out-root` and
`--run-name`. `--check-config` validates both stages without predictions.

MCP `iterative_design_plan` accepts the same stage options in `arguments` and
imports the RFdiffusion3 target into its content-addressed inputs. The CLI
`studioctl.py plan-iterative request.json` uses the same planner. Start only the
returned plan ID/digest. Plans retain both stages' code/runtime identities and
weights; no extra system Python, Git or compilation tools are needed by users.

On disk, `initialization_request.json` describes the recipe,
`initialization.json` records the audited handoff, `_initialization/` contains
raw generation outputs, and `refinement_template.yaml` records the later-stage
input policy. Results remain in the established `run_###/cycle_##` layout.
