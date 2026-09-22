# iProteinStudio

A native macOS application for protein structure prediction and design on Apple
Silicon. Choose a workflow, install its engines, and run it locally through guided
forms, a shared job queue and an interactive structure/results browser.

**[Download the app](https://github.com/t-j-fryer/iProteinStudio/releases)** ·
**[Install](docs/INSTALL_UNSIGNED_BETA.md)** ·
**[Documentation](docs/README.md)** · **[Updates](docs/UPDATES_AND_RELEASES.md)**

## Install and update

Download the Apple-silicon DMG from the newest **app** release (`v…-beta`), move
**iProteinStudio** to Applications, and follow the [first-launch guide](docs/INSTALL_UNSIGNED_BETA.md).
The separate `runtimes-…` release holds engine packages for Studio to download;
users do not install those archives manually.

Current releases are trusted betas: ad-hoc signed, with Sparkle-signed update
archives, but not Apple Developer ID signed or notarized. See [licensing status](LICENSING.md).

- **App:** macOS 14 or later, Apple Silicon.
- **Protenix v2/Mini packages:** macOS 26.0 or later.
- **OpenFold3/RFdiffusion3 packages:** macOS 26.2 or later.
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

## Workflows

| Workflow | Purpose |
| --- | --- |
| **Protein Hunter** | Iterative minibinder, nanobody and peptide design, with selectable prediction engines and independent verification. |
| **NISE** | Ligand-focused sequence search with Boltz structural/affinity checks and optional experimental NESSO or PSICHIC screening. |
| **RFdiffusion3** | Backbone generation, partial diffusion and motif scaffolding, followed by sequence design and prediction. |
| **Predict** | Structure prediction from sequences, FASTA or CSV, with explicit per-chain alignment and optional template settings. |

Colon-separated protein sequences define separate chains. Natural targets can
use cached or requested MSAs; de-novo chains use explicit single-sequence inputs.
Missing requested inputs cause an error rather than a silent change of method.
Remote MSA requests send the relevant sequences to an external service; see
[Privacy](PRIVACY.md).

## Engines

| Role | Available choices |
| --- | --- |
| Structure prediction | Boltz-2, IntelliFold Flash/full, Protenix v2/Mini, OpenFold3/MLX |
| Experimental guided proposals | Protenix Constraint, separate from unconstrained validation |
| Sequence design | ProteinMPNN, SolubleMPNN, LigandMPNN, AbMPNN, AntiFold, LASErMPNN |
| Backbone generation | RFdiffusion3/MLX |
| Experimental ligand screening | NESSO-1 and PSICHIC-XL |

Engine settings and schedules follow the app's qualified profiles. Confidence
scores remain engine-specific; they are not experimental evidence of binding.
[Screening policies](docs/NESSO_SCREENING.md) explain the distinct NESSO and
PSICHIC scores. [Runtime documentation](docs/PORTABLE_RUNTIME_IMPLEMENTATION.md)
records package identities, compatibility, recovery and qualification limits.

## Jobs and results

All four workflows and MCP clients use the same managed execution queue.
Submitted jobs continue when the app closes. Completed checkpoints remain on
disk; supported **Resume** actions use the saved settings and retained runtime.
Projects, alignments and results live under `~/.iproteinstudio`, outside the app.

Results keep trajectories, cycles, backbones and sequence derivatives together.
A saved hit belongs to its independently checked output. Cycle 00 is an initial
structure, not an optimized design. See [Job queue](docs/JOB_QUEUE.md),
[Results](docs/RESULTS.md) and [Storage](docs/OUTPUT_STORAGE.md).

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

Current-machine qualification is recorded in the [Lab Book](LAB_BOOK.md).
Fresh-Mac, other-chip and long-term acceptance remain distinct checks; their
absence is not hidden by successful local tests. Historical experiments are
retained as evidence, with dated research separated from current user guides.

[Support](SUPPORT.md) · [Security](SECURITY.md) · [Licensing](LICENSING.md) ·
[Third-party notices](THIRD_PARTY_NOTICES.md)
