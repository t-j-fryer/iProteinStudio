# iProteinStudio

A native macOS application for protein structure prediction and design on Apple
silicon. Studio connects established scientific tools into guided workflows,
manages their dependencies, and runs inference on your Mac's GPU. No cloud GPU,
Studio subscription, containers or manually configured Python environments are
required for supported local workflows.

**[Download the app](https://github.com/t-j-fryer/iProteinStudio/releases)** ·
**[Install](docs/INSTALL_UNSIGNED_BETA.md)** ·
**[Walkthroughs](docs/QUICKSTART.md)** · **[Documentation](docs/README.md)** ·
**[AI assistants](docs/AI_ASSISTANTS.md)**

## Install and update

Download the Apple-silicon DMG from the newest **app** release (`v…-beta`), move
**iProteinStudio** to Applications, and follow the [first-launch guide](docs/INSTALL_UNSIGNED_BETA.md).
The separate `runtimes-…` release holds engine packages for Studio to download;
users do not install those archives manually.

Current releases are trusted betas: ad-hoc signed, with Sparkle-signed update
archives, but not Apple Developer ID signed or notarized. See [licensing status](LICENSING.md).

- **App:** macOS 14 or later, Apple Silicon.
- **Protenix v2/Mini packages:** macOS 26.0 or later.
- **OpenFold3/RFdiffusion3/ESMFold2 packages:** macOS 26.2 or later.
- **Setup:** internet access and disk space for the engines and weights selected
  in **Engines**. Released portable packages do not require Xcode, Command Line
  Tools, Git, Homebrew or a separately installed Python.

The app contains its interface and pipeline adapters. Python runtimes and engine
software download from versioned GitHub Releases; model weights download
separately from their approved upstream hosts. Studio verifies checksums before
activation and offers retry for incomplete components.

After installing a distribution build, use **iProteinStudio → Check for Updates…**
or enable automatic checks in **Settings → Updates**. Sparkle reads the update
feed and downloads the signed app archive from GitHub Releases. Engines and model
weights remain separate, explicitly selected downloads. See
[how releases reach users](docs/UPDATES_AND_RELEASES.md).

## Predict, design and inspect

Use **New Prediction** for a fold, or create a **Workspace** to keep a design
project together. Within a workspace, **Predict** folds existing sequences;
**Design** opens the three design methods below.

| Workflow | Purpose |
| --- | --- |
| **Protein Hunter** | Iterative minibinder, nanobody and peptide design. Choose starting backbones and refinement engines separately, compare engine campaigns, and check candidates with other predictors. |
| **NISE** | Small-molecule binder search from Protein Hunter or RFdiffusion3 starts. Boltz structure/affinity optimisation, with experimental NESSO/PSICHIC screening or selection objectives. |
| **RFdiffusion3** | Backbone generation, partial diffusion and motif scaffolding, followed by sequence design and prediction. |
| **Predict** | Structure prediction from sequences, FASTA or CSV, with explicit per-chain alignments and templates where supported. |

Protein Hunter supports nanobody scaffold selection, engine-specific target
templates and hotspots, and an initialization-only secondary-structure control.
Its [starting/refinement stages](docs/PROTEIN_HUNTER_STAGES.md) can combine
hallucination or RFdiffusion3 backbones with complete-sequence refinement,
including experimental ESMFold2. [NISE](docs/NISE.md) integrates backbone
generation, sequence proposals, ligand geometry checks and iterative selection.
These are Studio workflow extensions around upstream methods; the prediction
models and sequence-design algorithms retain their original attribution.

Follow the [step-by-step walkthroughs](docs/QUICKSTART.md) for a first prediction,
protein binder, small-molecule binder or saved-result review.

Colon-separated protein sequences define separate chains. Natural targets can
use cached or requested MSAs; de-novo chains use explicit single-sequence inputs.
Missing requested inputs cause an error rather than a silent change of method.
Remote MSA requests send the relevant sequences to an external service; see
[Privacy](PRIVACY.md).

## Engines

| Role | Available choices |
| --- | --- |
| Structure prediction | Boltz-2, IntelliFold v2 Flash/full, Protenix v2/Mini, OpenFold3/MLX; experimental ESMFold2 Fast/Full MLX |
| Experimental guided proposals | Protenix Constraint, separate from unconstrained validation |
| Sequence design | ProteinMPNN, SolubleMPNN, LigandMPNN, AbMPNN, AntiFold, LASErMPNN |
| Backbone generation | RFdiffusion3/MLX |
| Experimental ligand screening | NESSO-1 and PSICHIC-XL |

Engine settings and schedules follow the app's qualified profiles. Confidence
scores remain engine-specific; they are not experimental evidence of binding.
[Screening policies](docs/NESSO_SCREENING.md) explain the distinct NESSO and
PSICHIC scores. [Runtime documentation](docs/PORTABLE_RUNTIME_IMPLEMENTATION.md)
records package identities, compatibility, recovery and qualification limits.
See [prediction settings](docs/PREDICTION_PROFILES.md) for compute budgets and
[ESMFold2](docs/ESMFOLD2.md) for its additional memory, input and workflow limits.

## Jobs and results

All four workflows and MCP clients use the same managed execution queue.
Submitted jobs continue when the app closes. Completed checkpoints remain on
disk; supported **Resume** actions use the saved settings and retained runtime.
Projects, alignments and results live under `~/.iproteinstudio`, outside the app.

Results keep trajectories, cycles, backbones and sequence derivatives together.
A saved hit belongs to its independently checked output. Cycle 00 is an initial
structure, not an optimized design. See [Job queue](docs/JOB_QUEUE.md),
[Results](docs/RESULTS.md) and [Storage](docs/OUTPUT_STORAGE.md).

## AI assistants and automation

The **AI** toolbar button connects supported desktop assistants to Studio's
Model Context Protocol (MCP) bridge. Choose read-only access for reviewing work,
or read-and-run access for planning and executing workflows. The assistant uses
the same local queue, saved inputs and results as the app. Supported workflow
recipes and engine/scaffold batches use the existing planners; selected
candidates can be exported with sequences, structures, scores and provenance.
Optional [RCSB discovery](docs/AI_ASSISTANTS.md#optional-rcsb-discovery) adds
structure search and residue mapping through the official RCSB MCP server.

The [assistant guide](docs/AI_ASSISTANTS.md) covers setup, tool order, examples,
current GUI/MCP differences and an optional portable operating skill. Local
protein-model inference does not require an AI assistant; a chosen assistant or
remote MSA service may use external infrastructure. Remote access is opt-in.

## Development

Building Studio from source requires the macOS Swift toolchain and SDK; this is
separate from running a downloaded app or installing portable engines.

```bash
./build_app.sh
open build/iProteinStudio.app
```

Start with [Architecture](ARCHITECTURE.md), [Testing](docs/TESTING.md) and
[CLI/MCP](docs/CLI.md). Scientific implementations originate upstream; Studio
owns integration, reproducible requests, installation, job management and UI.

Measured performance and qualification limits are recorded in the
[Lab Book](LAB_BOOK.md). Memory requirements depend on the model and input size.

[Support](SUPPORT.md) · [Security](SECURITY.md) · [Licensing](LICENSING.md) ·
[Third-party notices](THIRD_PARTY_NOTICES.md)
