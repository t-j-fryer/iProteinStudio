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
- **OpenFold3/RFdiffusion3/RFD4/ESMFold2 packages:** macOS 26.2 or later.
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

## Design by intention

**Design** offers recommended workflows, a custom builder and reusable saved
workflow buttons. Choose monomers, minibinders, nanobodies, small-molecule
binders, motif scaffolding or optimization of an existing structure. The builder
shows methods suitable for that intention; saved buttons reopen editable settings.

| Recommended workflow | Starting structure and assessment |
| --- | --- |
| Minibinder / nanobody · easy | Native RFD4 generation followed by ESMFold2 Full scoring |
| Minibinder / nanobody · hard | RFD4 starts, then SolubleMPNN / AbMPNN proposals and Full refolding, up to seven beam cycles |
| Small-molecule binder · easy | Native RFD4 followed by Boltz P(bind) + ligand pLDDT/100 |
| Small-molecule binder · hard | RFD4 starts, LASErMPNN beam exploration and the same Boltz objective |

These are configured starting workflows, not experimentally established target
difficulty classes or universal success rankings. Supply the target, optional
hotspots and active design time. Protein targets may be structures or complete
sequences separated by `:`. Sequence targets are prepared as an assembly with
ESMFold2 Full and per-chain MSAs before design. Target preparation has a separate
time budget; queue time does not count toward active design time.

| Custom method | Capabilities |
| --- | --- |
| **RFD4** | Joint sequence/structure generation; monomers, protein/ligand binders, supported nanobody frameworks, structural motifs, partial diffusion, inverse folding and native conditions. Fixed, iterative, greedy and beam sequence exploration; separate native rollout search. |
| **RFdiffusion3** | Backbone generation, unconditional monomer starts, partial diffusion and structural motif scaffolding, followed by sequence design and prediction. |
| **X-token Hallucination** | Original Protein Hunter algorithms for compatible monomer/binder starts, CDR design, sequence-motif preservation and partial sequence redesign. Full supports fixed-framework CDR-only starts; whole-chain ESMFold2 X-token generation is unsupported. |
| **NISE** | Small-molecule search with Boltz structure/affinity selection and optional experimental NESSO/PSICHIC screening or objectives. |
| **Template-guided Boltz motif beta** | Design → Motif scaffolding → Atomic motif beta. Pinned AME-41 motifs, explicit residue maps, RFD3 starts, mapped template guidance and separate untemplated ranking checks. Bounded 1–5-root pilots. |
| **Predict** | Complete sequences, FASTA or CSV, with per-chain alignments and templates where supported. |

RFD3 fixed-framework nanobody generation was tried unsuccessfully and is excluded.
The motif beta has CPU input/feature checks and a bounded end-to-end KSI
test covering both designers, guided/untemplated predictions and pause/resume.
This is software qualification, not general design performance or enzyme activity. Protenix/IntelliFold motif template exports have CPU checks
only. General custom-motif template-guided X-token scaffolding is not available.
See [RFD4](docs/RFD4.md), [motif beta](docs/MOTIF_BETA.md),
[Protein Hunter stages](docs/PROTEIN_HUNTER_STAGES.md) and [NISE](docs/NISE.md).

Colon-separated protein sequences remain separate chains throughout supported
workflows. Natural targets use requested/cached MSAs; de-novo chains use explicit
single-sequence inputs. Missing requested inputs cause an error rather than a
silent change of method. Remote MSA requests send relevant sequences to an
external service; see [Privacy](PRIVACY.md).

## Base setup and qualification

The base selection is **RFD4, ESMFold2 Full, Boltz-2 plus affinity, SolubleMPNN,
AbMPNN and LASErMPNN**. Studio resolves shared ESMC weights, managed Python and
engine environments, chemical data and libraries. Additional engines such as
RFD3 are optional. The complete base needs Apple Silicon and macOS 26.2+.

The RFD4 portable runtime is published for the 0.2.27 app release. The complete base
selection passed installation and detection in an isolated, initially empty root
with no preseeded model files or external developer tools. A second physical Mac
remains outside this qualification. See
[release qualification](lab_book/0579-qualify-and-release-studio-027.md). RFD4 and guided beta memory
estimates are not calibrated, so their visible memory override is an explicit,
recorded choice. Existing installed workflows and their saved runtime identities
remain separate from these qualification limits.

## Engines

| Role | Available choices |
| --- | --- |
| Structure prediction | Boltz-2, IntelliFold v2 Flash/full, Protenix v2/Mini, OpenFold3/MLX; experimental ESMFold2 Fast/Full MLX |
| Experimental guided proposals | Protenix Constraint, separate from unconstrained validation |
| Sequence design | ProteinMPNN, SolubleMPNN, LigandMPNN, AbMPNN, AntiFold, LASErMPNN |
| Backbone generation | RFdiffusion3/MLX; experimental RFD4 integration |
| Experimental ligand screening | NESSO-1 and PSICHIC-XL |

Engine settings and schedules follow the app's qualified profiles. Confidence
scores remain engine-specific; they are not experimental evidence of binding.
[Screening policies](docs/NESSO_SCREENING.md) explain the distinct NESSO and
PSICHIC scores. [Runtime documentation](docs/PORTABLE_RUNTIME_IMPLEMENTATION.md)
records package identities, compatibility, recovery and qualification limits.
See [prediction settings](docs/PREDICTION_PROFILES.md) for compute budgets and
[ESMFold2](docs/ESMFOLD2.md) for its additional memory, input and workflow limits.

## Jobs and results

All workflows and MCP clients use the same managed execution queue.
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

The CLI and MCP expose typed RFD4 and motif-beta plans through the shared queue.
The bundled [workflow evidence reference](Sources/iProteinStudio/Resources/pipeline/mcp/skills/iprotein-studio/references/evidence.md)
helps assistants distinguish measured findings, bounded technical checks and
user-defined presets. Current campaign data is reviewed through the result tools,
not treated as a universal engine leaderboard.

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
