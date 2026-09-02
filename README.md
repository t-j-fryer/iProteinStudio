# iProteinStudio

A native macOS app for designing protein binders on Apple Silicon — with a
guided setup, clean design forms, and a **live dashboard** showing metrics
updating in real time and the 3D structure of every hit.

Built for people who want to design binders without touching a terminal.

![status](https://img.shields.io/badge/status-alpha-orange)

## What it does

**Iterative design** — paste a target sequence or SMILES, pick a validated
nanobody scaffold or a de-novo binder size, choose your design engine, and watch
iPTM climb per cycle. Designs that pass your hit threshold are re-folded with an
independent model, because a design engine scoring its own designs is marking its
own homework. Protein interfaces also report conservative `ipSAE(min)` whenever
the selected predictor emits PAE (Boltz, IntelliFold, or Protenix).

**RFdiffusion3** — generate binders de novo, locally explore an existing bound
structure with partial diffusion, or scaffold explicit functional motif atoms
into a new binder. Mode-specific worked p53–MDM2 examples make the two
structure-guided workflows directly runnable. Motif campaigns retain the exact
source-residue → designed-residue map, protect those residues through MPNN, and
score recovery of the selected atoms after independent prediction. For small
molecules, click ligand atoms to request burial, exposure or hydrogen bonding;
the full pipeline runs backbones → LASErMPNN → Boltz-2 affinity/apo checks.

**Predict** — fold sequences you already have, with no design involved. Paste
them, or bring a FASTA or CSV; fold as monomers, all against one partner, or each
with its own. Alignments are per chain, so a de-novo binder can be folded from its
single sequence while its target gets a deep MSA — and every alignment this
machine has ever made is reused rather than re-fetched. Multimers retain the
directional and pairwise ipSAE values behind the displayed `ipSAE(min)` summary;
OpenFold is left blank because its current detailed output is PDE rather than PAE.

Across all protein inputs, a colon separates subunits: `SEQUENCE_A:SEQUENCE_B`.
Studio immediately shows the detected chain map. Plain prediction assigns A, B,
C… in input order. Design workflows reserve A for the new binder and assign the
fixed target B, C, D…. External RFdiffusion3 PDB/mmCIF chains are read using
their original names and copied into that backend-safe convention automatically.

**One-click setup** — installs pinned engine revisions and verified model weights
under iProteinStudio's own managed root. A new user does not need NanoHunter or
any developer-machine Python or model cache. Environments are hash-locked,
staged and health-checked before an atomic version switch; interrupted model
downloads resume, and optional large checkpoints can be installed or removed
independently. Reusing an existing NanoHunter remains an explicit disk-saving
option.

## Engines

| | |
|---|---|
| Structure prediction | Boltz-2 (± steering potentials), Protenix v2/Mini on native MPS, IntelliFold PyTorch/Metal, OpenFold-3/MLX |
| Epitope-guided iterative proposals | Boltz-2 steering potentials; experimental Protenix Constraint v0.5 pocket guidance on native MPS |
| Sequence design | AntiFold, AbMPNN, ProteinMPNN, SolubleMPNN, LigandMPNN, LASErMPNN |
| Backbone generation | RFdiffusion3 on MLX |

Boltz-2 is the default design engine: on the reference benchmark it is roughly
3.4× cheaper per design than the slowest alternative and needs only one process.
The others are offered with their real measured cost shown, so the trade is
visible rather than guessed at.

Protenix v2 is the accuracy-first option and Mini is a faster preview. They
share one install and the same cached A3Ms, run only on the Apple GPU, and never
fall back to CPU. Protenix can acquire a missing MSA through its own public
server client; it does not require Boltz or local genetic databases.

**Protenix Constraint v0.5 is separate and experimental.** It is an optional,
design-only checkpoint for proposing protein binders toward a selected epitope;
it is not installed with Protenix v2/Mini and cannot be used as an independent
structure checker. Setup gives it an isolated ESM-free environment, downloads
and verifies the exact constraint checkpoint, and refuses CPU fallback. Its
upstream 8 Å setting is a learned token-centre pocket prior—not a heavy-atom
contact cutoff—and the first paired acceptance showed weak alternative-pocket
steering. Final sequences should therefore be re-folded with an independent
unconstrained model rather than treated as validated binders.
Existing installs may show this component as needing an update after upgrading
Studio: repair reapplies the pinned native-MPS source patches and reuses a valid
1.48-GB checkpoint rather than downloading it again.

AlphaFold 3 and IntelliFold's JAX/Metal path are deliberately not offered. Both
failed same-input Apple-GPU quality control while IntelliFold PyTorch produced a
credible structure from the same alignment. Historical results remain readable;
the evidence and retirement boundary are recorded in [Lab Book 0029](lab_book/0029-retire-untrusted-jax-metal-predictors.md).

## Requirements

- macOS 14+ on Apple Silicon
- Xcode Command Line Tools (`xcode-select --install`)
- Internet access for first-run setup (downloads are several GB)

## Unsigned beta installation

Until a Developer ID-signed release is available, controlled second-Mac builds
are distributed as an explicitly labelled unsigned beta DMG. macOS requires a
one-time **Privacy & Security → Open Anyway** confirmation; after that, the app
can receive update archives verified with the project's Sparkle EdDSA key. See
[Install the unsigned beta](docs/INSTALL_UNSIGNED_BETA.md)
before opening one.

Every beta release includes SHA-256 checksums and build provenance. Model engines
and checkpoints are not embedded in the DMG; the user reviews and confirms those
separate downloads in the app.

## Build & run

```bash
./build_app.sh
open "build/iProteinStudio.app"
```

Or during development:

```bash
swift build && swift run
```

To work on it in Xcode, `open Package.swift`.

## How it works

Studio is a front end: the scientific implementations originate in NanoHunter
and upstream engine repositories, and Studio ports their validated behaviour
rather than reimplementing it. The app bundle contains the pipeline, the
IntelliFold PyTorch/Metal, Protenix v2/Mini and Protenix Constraint MPS patches
and dependency locks, RFdiffusion3's complete script overlay, worked examples,
seven nanobody scaffolds, and their sequence-validated deep MSAs.
Setup clones pinned upstream revisions and installs everything beneath the
space-free managed root `~/.iproteinstudio/`; no sibling checkout is required.

Runs are written to separate, durable directories. The global Activity panel and
per-project history show completed, failed, active and interrupted work after a
restart, with Reveal and checkpoint Resume where the recorded command supports
it. RFdiffusion3 campaigns can run for days, so Studio also reattaches to their
live PID after relaunch. Accepted RFdiffusion3 backbones and verification folds
appear in a live structure browser as they are written, alongside score
histograms, saved hit-filter verdicts and motif correspondence. Every workload
is launched under `caffeinate` for its actual lifetime so a sleeping Mac does
not strand a GPU campaign.

Large confidence arrays are retained losslessly as checksum-verified gzip files;
selected structures, galleries and batch logs use references rather than duplicate
copies. Exact MSAs and campaign policy snapshots share content-addressed APFS
storage while every run remains independently resumable. See
[Output storage and retention](docs/OUTPUT_STORAGE.md).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design, and
**[LAB_BOOK.md](LAB_BOOK.md) for why things are the way they are** — every
measurement, decision and dead end is recorded there.

Distribution and support documents: [Privacy](PRIVACY.md),
[Security](SECURITY.md), [Support](SUPPORT.md),
[Licensing status](LICENSING.md), and
[Third-party notices](THIRD_PARTY_NOTICES.md).

## What a fresh install gets, and how updates reach people

Everything needed to run is shipped **inside the app bundle** and written out on
first launch:

| Layer | What it is | Where it comes from |
|---|---|---|
| Pipeline | `nanohunter_run.sh` and its helper scripts | vendored from NanoHunter by `tools/sync_pipeline.sh` |
| Studio helpers | prediction batching, ligand analysis, campaign preparation | written here |
| Engine profiles | pinned Apple-MPS patches and dependency locks, including the isolated Protenix Constraint v0.5 profile | shipped in the app bundle and staged before setup |
| RFdiffusion3 overlay | the whole RFD3 script layer — campaign orchestrators, ligand preparation, predictor adapters, length binning | vendored by `tools/sync_rfd3.sh` |

The last one matters more than it sounds: **none of it is upstream**. A clean
clone of the RFdiffusion3 MLX port contains zero of those scripts, so without the
overlay a new user gets a checkout that cannot run anything. The installer
applies it straight after cloning, before RFdiffusion3's own installer runs —
which is necessary, because that installer calls scripts the overlay provides.

The heavy parts — Python environments and model weights — are downloaded by
`setup_pipeline.sh` on first run. Source revisions, critical package versions,
checkpoint sizes and downloaded hashes are pinned; an incomplete or changed
artifact fails setup. The optional Protenix Constraint component owns a separate
environment, source checkout and model directory so its ESM-free checkpoint
contract cannot contaminate Protenix v2/Mini. Existing NanoHunter/RFD3
installations can be linked explicitly, then materialised into real local copies
when a fully standalone root is wanted; all three constraint directories follow
that reuse/materialisation path too.

**Updates.** Version 0.2 introduces Sparkle-based application updates with clear
release notes and user controls for automatic checking/downloading. The bundled
scripts are re-staged after an app update, while environments and weights remain
untouched. Engines and checkpoints are never automatic: Studio shows their
purpose and approximate footprint and requires a final confirmation before any
large download. Copies older than 0.2 require one manual upgrade to the first
trusted beta or signed release. Trusted betas verify update archives with the
project's Sparkle EdDSA key but remain ad-hoc signed and unnotarized by Apple.
Public delivery remains blocked until a Developer ID certificate is installed
and the first notarized cross-version update is accepted on a second Mac. See
[Application and engine updates](docs/UPDATES_AND_RELEASES.md).

## Working on this repo

Read [CLAUDE.md](CLAUDE.md) first. Any AI agent working here is required to
record what it did in the Lab Book, including what it did not test.

## Status

Alpha. Builds and runs. Complete protein RFdiffusion3 and nanobody routes have
local Apple-GPU acceptance evidence, but the app is not signed or notarised; see
the Known gaps list at the top of [LAB_BOOK.md](LAB_BOOK.md).
