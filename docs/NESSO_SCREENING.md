# Optional NESSO screening for small-molecule designs

Enable **Screen with NESSO before structural verification** in Protein Hunter's
model settings or RFdiffusion3's verification settings. It is off by default and
appears only for small-molecule targets. Set **Maximum sequences to advance**
(default 20), then choose Boltz 2, IntelliFold Flash/full, Protenix Mini/v2 or
OpenFold3 for structural verification. Install the requested components in
**Engines** before starting. NESSO installs its pinned ESM-2 dependency itself;
no separate ESM installation is needed.

## Where the screen runs

| Workflow | Candidates scored by NESSO | Shortlist scope | What happens next |
|---|---|---|---|
| Protein Hunter | Every completed optimized cycle in the campaign's `summary_all_runs.csv`; cycle 00 is excluded | Top X per selected design-engine campaign, across all its trajectories and cycles | The chosen predictor folds the selected sequences with the ligand |
| RFdiffusion3 | All MPNN sequences, after backbone generation and inverse folding | Top X across all backbones and sequence derivatives | The chosen predictor folds the selected sequences with the ligand |
| NISE | Its independently enabled initial and/or optimization screens | Existing stage-specific lineage and trajectory limits | Boltz performs the existing pocket, exposure and structural checks |

Protein Hunter finishes its normal design cycles and any configured independent
checks before this additional stage. NESSO does not alter those cycles or their
hit classifications. With several design engines selected, each engine has its
own top-X shortlist. Repeated sequences remain separate designs with their
original run/cycle or backbone/derivative identity; this is not a sequence-diversity
filter. There is no one-per-lineage cap in these two campaign-wide screens.

In RFdiffusion3, enabling NESSO selects a different verification route. The
standard all-sequence Boltz affinity folds, Boltz ranking, extra predictors and
apo checks are inactive in this route. They reappear when NESSO is switched off.
The saved execution payload explicitly disables these inactive stages; the
project retains their form settings. Atom conditioning during RFdiffusion3
backbone generation is unchanged.

## Ranking and interpretation

Current screening uses:

`NESSO P(bind) + (1 − entropy_crop_pl)`

`entropy_crop_pl` is normalized, pocket-cropped protein–ligand placement entropy.
The [NESSO output documentation](https://github.com/recursionpharma/nesso/blob/main/docs/prediction.md#output-files)
recommends cropped interface entropy and identifies zero cropped entropy as an
unreliable placement. Full `entropy_pl` remains available as a diagnostic.
This corrects build 30's use of full entropy. The current policy is
`nesso-pbind-placement-v2`; historical results retain their recorded policy.

An eligible candidate needs finite entropy in **(0.000001, 1]** and finite P(bind)
in [0, 1]. The lower cutoff is a Studio numerical guard, not an experimentally
validated biological threshold. Missing, zero, near-zero or otherwise invalid
entropy excludes the candidate before applying the shortlist limit. An invalid
probability is an execution error. Highest combined score wins; candidate name
breaks exact ties reproducibly. If fewer than X candidates qualify, Studio folds
those available. If none qualify, it saves the rejection report and stops.

This is an experimental screening heuristic, **not NESSO ligand pLDDT**. The sum
is not a calibrated binding probability. Accuracy on designed binders has not
been established. Structural scores remain separate and do not automatically
make a shortlisted design a hit.

## Structural verification and files

The new campaign-wide verification folds receive the exact same ligand SMILES
as NESSO, with protein chain A, ligand chain B, and explicit empty protein MSA.
They use the chosen predictor's established adapter and settings. They have no
pocket restraint, structure template, Boltz affinity head or apo comparison.
These are independent folds; earlier design restraints do not imply that these
new predictions satisfy atom burial/exposure requirements. NISE's own Boltz
checks remain governed by [NISE settings](NISE.md).

Each campaign contains a `nesso_verification` folder:

- `config.json`: frozen options, ligand SMILES, candidate source and dependency digest.
- `nesso_screening.csv`: every candidate, identity, sequence, score components,
  eligibility, rejection reason and selection decision.
- `scores/<candidate>/`: raw NESSO outputs, ligand-identity audit and completion receipt.
- `selection.json`: the exact ranking policy and shortlist.
- `prediction_inputs/`, `prediction_command.json`, `prediction.log`: predictor inputs and execution record.
- `folds/` and `fold_receipts/`: structural outputs and per-design completion receipts.
- `results.json`: selected structures with separate NESSO and structure scores.

Open campaign results to see **NESSO shortlist verification**. Open the campaign
folder to inspect the complete CSV, including candidates that were never folded.
The MCP results catalog also lists this table. The new options are currently
native-app settings; the public MCP iterative/RFdiffusion request schemas have
not been extended with a NESSO option.

## Interruption, dependencies and throughput

The native broker preflights the requested NESSO installation and exact verifier
checkpoint before starting the campaign. It freezes code and a digest of model
and script dependencies and retains the shared Apple GPU execution lease across
the design and screening stages. No weights are copied into the run or app.

One resident NESSO process loads NESSO and ESM once for pending candidates, then
closes before structure prediction. The shared predictor runner retains its
existing measured scheduling policies: resident Boltz/IntelliFold/Protenix Mini,
full Protenix v2 directory waves, and OpenFold3's existing per-input adapter.
This change introduces no new throughput measurements or claims.

Resume audits the candidate source, options and saved artifacts. It reuses
completed NESSO scores and verified folds. Successful folds from a partially
failed batch are checkpointed. Unreceipted partial fold directories are moved
to `interrupted_folds` before retry; they are never accepted merely because a
CIF exists. Changed inputs, dependencies or completed artifacts fail explicitly.
Use a new campaign to change the ligand, shortlist size, model or ranking policy.
