# Your first workflows

Install the app using the [first-launch guide](INSTALL_UNSIGNED_BETA.md).
Open **Engines**, select the models you need, and let Studio download their
runtimes and weights. Wait for the required engines to report installed before
starting. The app manages dependencies; model size and macOS requirements still
apply. Start small while establishing a workflow on your Mac.

## Predict a structure

1. Choose **New Prediction**, or **Predict** within an existing workspace.
2. Enter sequences or import FASTA/CSV. Separate chains explicitly; colon-separated
   sequences represent separate protein chains.
3. Select an installed prediction engine. Set each chain's MSA policy: a natural
   protein can use an imported/cached alignment or an explicit server request;
   a designed chain uses an empty alignment. Templates are engine-specific.
4. Review **Prediction accuracy & compute**, then submit. Open **Jobs** to follow
   progress; completed structures appear as the job publishes them.
5. Open the saved prediction to inspect structures, scores and outputs.

Remote MSA requests send sequences to the configured service. Missing requested
alignments fail instead of silently changing the experiment. See
[prediction settings](PREDICTION_PROFILES.md), [templates](PREDICTION_TEMPLATES.md)
and [ESMFold2](ESMFOLD2.md).

## Design a protein binder with Protein Hunter

1. Create/open a **Workspace**, choose **Design → Protein Hunter**, and provide
   the protein target and binder type.
2. Choose **Starting backbones · cycle 00**: the refinement engine itself,
   a separate hallucination engine, or RFdiffusion3. RFdiffusion3 starts require
   a target structure; **Predict target structure…** can prepare one first.
3. Select refinement engines, trajectories per engine and optimisation cycles.
   For nanobodies, choose the scaffold allocation. Each engine receives the full
   trajectory budget; selecting more engines increases the total work.
4. Choose the sequence designer and independent checks. SolubleMPNN is the
   default for soluble protein de-novo binders; use the supported antibody
   designers for the selected nanobody workflow. Apply hotspots or target
   templates only where the selected engines support them.
5. Run a small complete trial, then inspect each trajectory and checked cycle.
   Cycle 00 is a starting structure; a later design is not a validated binder
   merely because its design engine reports high confidence.

The [stage guide](PROTEIN_HUNTER_STAGES.md), [engine guide](PROTEIN_HUNTER_ENGINES.md)
and [nanobody guide](NANOBODY_DESIGN.md) explain compatible combinations.

## Generate backbones with RFdiffusion3

1. Choose **Design → RFdiffusion3**, then de novo design, partial diffusion or
   motif scaffolding.
2. Supply the target/complex and select chains. Use surface scanning for an
   unknown protein epitope; use explicit hotspots for a chosen site. Partial
   diffusion and motif scaffolding have their own structure/atom requirements.
3. Set backbone and sequence budgets. For soluble protein binders, start with
   SolubleMPNN and keep independent prediction/analysis enabled.
4. Complete 1–5 backbones through the full workflow before a new campaign over
   10. Inspect backbone → sequence derivative → checked complex/binder outputs.

See the [RFdiffusion3 input contracts](CLI.md#rfdiffusion3) for advanced controls.
RFdiffusion3 DNA/RNA design is not exposed by Studio.

## Search for a small-molecule binder with NISE

1. Choose **Design → NISE**, supply the ligand, and review any selected binding
   or exposed-atom requirements against its current atom map.
2. Under **Initial backbone generation**, choose Protein Hunter or RFdiffusion3
   and a small starting budget.
3. Under **NISE optimisation**, set proposal counts, beam and stopping rules.
   Boltz selection is the default. Optional NESSO/PSICHIC screening and their
   alternative optimisation objectives are distinct experimental choices.
4. Submit and inspect initial lineages, optimisation cycles, ligand placement
   and saved selection scores. Computational scores do not establish binding.

The [NISE guide](NISE.md) defines the stages, geometry filters and objectives;
[ESMFold2](ESMFOLD2.md) describes its optional unrestrained structure-generation
route with NESSO/PSICHIC objectives.

## Review, stop or resume

Use workspace **Runs**, the **All Runs** library or **Activity** to revisit work.
**Jobs** shows queued/running jobs and their progress logs. Closing the window
does not stop a submitted job. Use **Stop** to cancel; supported **Resume**
actions continue the saved experiment. Editing today's form does not modify an
existing job's settings. See [jobs](JOB_QUEUE.md) and [results](RESULTS.md).

For natural-language control of these workflows, see
[AI assistants](AI_ASSISTANTS.md).
