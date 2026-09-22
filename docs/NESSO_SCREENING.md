# Experimental sequence screening for small-molecule designs

Enable **Experimental sequence screening before structural verification** in
Protein Hunter's model settings or RFdiffusion3's verification settings. It is
off by default and appears only for small-molecule targets. Choose **Scoring
engine**, set **Maximum sequences to advance** (default 20), then choose **Fold
shortlist with**. Install the selected scorer and verifier in **Engines** first;
each scorer includes its own required ESM dependency.

| Scorer | Ranking, highest first | Interpretation |
|---|---|---|
| NESSO (experimental) | P(bind) + (1 − `entropy_crop_pl`) | Binding likelihood plus a placement-confidence proxy; not ligand pLDDT or a calibrated probability |
| PSICHIC (experimental) | 1 − `predicted_nonbinder` | Binding-class likelihood; no placement-confidence term. Affinity and antagonist/nonbinder/agonist probabilities are saved separately |

Neither ranking has established experimental accuracy for designed binders.
Existing saved requests without an engine selection retain NESSO.

## Where the screen runs

| Workflow | Candidates | Shortlist scope | Next stage |
|---|---|---|---|
| Protein Hunter | All completed optimized cycles; cycle 00 excluded | Top X per design-engine campaign, across trajectories and cycles | Selected predictor folds the shortlist with the ligand |
| RFdiffusion3 | All MPNN sequences after backbone generation and inverse folding | Top X across backbones and sequence derivatives | Selected predictor folds the shortlist with the ligand |
| NISE | Independently enabled initial and/or optimization screens | Stage-specific lineage and trajectory limits | Boltz performs the existing pocket, exposure and structural checks |

Protein Hunter completes its normal cycles and configured independent checks
before this additional stage. Screening does not change their hit verdicts.
Repeated sequences retain separate run/cycle or backbone/derivative identities;
this is not a diversity filter. These two campaign-wide screens have no
one-per-lineage cap. NISE retains its own [stage policy](NISE.md#optional-sequence-screening-experimental).

In RFdiffusion3, screening selects an alternative verification route. The
standard all-sequence Boltz affinity folds, Boltz ranking, extra predictors and
apo checks become inactive. Switching screening off restores their saved form
settings. Backbone atom conditioning is unchanged.

## NESSO eligibility

`entropy_crop_pl` is normalized, pocket-cropped protein–ligand placement entropy.
The [upstream output guide](https://github.com/recursionpharma/nesso/blob/main/docs/prediction.md#output-files)
recommends cropped interface entropy and identifies zero cropped entropy as an
unreliable placement. Full `entropy_pl` is retained only as a diagnostic.
Current policy is `nesso-pbind-placement-v2`; historical results retain their
recorded policy.

Candidates need finite entropy in **(0.000001, 1]** and finite P(bind) in [0, 1].
The lower entropy cutoff is a Studio numerical guard, not a biological
threshold. Invalid placement excludes a candidate before the shortlist limit;
invalid probability is an execution error. Candidate name breaks ties. Fewer
than X eligible candidates yields a smaller shortlist; none yields a saved
rejection report and an explicit failure. PSICHIC has no entropy term and does
not use this placement filter.

## Verification and saved files

Campaign-wide verification uses the exact screening ligand SMILES, protein chain
A, ligand chain B and explicit empty protein MSA. The chosen predictor uses its
established adapter/settings, without pocket restraint, template, Boltz affinity
head or apo comparison. Earlier design restraints do not establish that these
independent folds satisfy burial/exposure requirements. NISE's separate Boltz
checks follow its own settings.

For saved-run compatibility, the campaign folder remains `nesso_verification`
for either scorer. It contains:

- `config.json`: frozen options, ligand, candidate source and dependency digest.
- `nesso_screening.csv` or `psichic_screening.csv`: all candidates, component
  scores, eligibility and shortlist decisions.
- `scores/<candidate>/`: raw scorer outputs and completion receipts.
- `selection.json`: exact ranking policy and shortlist.
- `prediction_inputs/`, `prediction_command.json`, `prediction.log`: fold inputs and execution record.
- `folds/`, `fold_receipts/`: structures and per-design receipts.
- `results.json`: screening and structural scores kept separate.

Results and the MCP catalog expose screening tables, including candidates that
were never folded. Public NISE requests use `screening_engine`; native campaign
screening payloads use `engine`. The public iterative/RFdiffusion MCP request
schemas do not yet expose those native screening controls. Legacy
`nesso_screen`/`phase0_nesso_screen` names remain for saved-request compatibility.

## Recovery and execution

The broker preflights the requested scorer and exact verifier, preserves code
and dependency bindings, and holds the shared Apple GPU lease. Weights are not
bundled in the app or copied into the scientific outputs.

NESSO reuses its loaded model and ESM process for pending candidates. PSICHIC's
current adapter uses ESM MPS batches of eight and CPU graph batches of sixteen,
with complete protein sequences up to 700 residues. It does not silently switch
to CPU ESM or another scorer. These are execution settings, not a claim of
measured speed on every Mac. The verifier keeps its existing engine scheduler.

Resume audits candidate sources, settings and receipts, then reuses completed
scores and folds. Unreceipted partial folds move to `interrupted_folds` before
retry. Changed inputs, dependencies or completed artifacts fail explicitly. Use
a new campaign to change the ligand, model, shortlist size or ranking policy.
