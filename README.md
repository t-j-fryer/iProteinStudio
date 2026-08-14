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
own homework.

**RFdiffusion3** — generate binder backbones from scratch against a protein or a
small molecule. Choose which ligand atoms end up buried, exposed, or hydrogen
bonded by clicking them in a list read out of your own molecule. Small-molecule
campaigns run the full pipeline: backbones → LASErMPNN sequences → Boltz-2 with
steering potentials and the affinity head → ranking by ligand pLDDT + P(bind) →
apo re-folding of the best designs to see whether the binding site is already
formed before the ligand arrives.

**Predict** — fold sequences you already have, with no design involved. Paste
them, or bring a FASTA or CSV; fold as monomers, all against one partner, or each
with its own. Alignments are per chain, so a de-novo binder can be folded from its
single sequence while its target gets a deep MSA — and every alignment this
machine has ever made is reused rather than re-fetched.

**One-click setup** — installs pinned engine revisions and verified model weights
under iProteinStudio's own managed root. A new user does not need NanoHunter or
any developer-machine model cache. Reusing an existing NanoHunter remains an
explicit disk-saving option.

## Engines

| | |
|---|---|
| Structure prediction | Boltz-2 (± steering potentials), IntelliFold (PyTorch **and** JAX/MPS), AlphaFold 3, OpenFold-3 |
| Sequence design | AntiFold, AbMPNN, ProteinMPNN, SolubleMPNN, LigandMPNN, LASErMPNN |
| Backbone generation | RFdiffusion3 on MLX |

Boltz-2 is the default design engine: on the reference benchmark it is roughly
3.4× cheaper per design than the slowest alternative and needs only one process.
The others are offered with their real measured cost shown, so the trade is
visible rather than guessed at.

AlphaFold 3 weights (`af3.bin`) are governed by Google's terms and are **not**
downloaded — obtain them from Google and place them where the setup screen says.

## Requirements

- macOS 14+ on Apple Silicon
- Xcode Command Line Tools (`xcode-select --install`)
- Internet access for first-run setup (downloads are several GB)

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
IntelliFold v2-flash JAX patch, RFdiffusion3's complete script overlay, worked
examples, seven nanobody scaffolds, and their sequence-validated deep MSAs.
Setup clones pinned upstream revisions and installs everything beneath the
space-free managed root `~/.iproteinstudio/`; no sibling checkout is required.

RFdiffusion3 campaigns can run for days, so they are launched detached and keep
going if you quit the app; reopening the project reattaches to the running
campaign.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design, and
**[LAB_BOOK.md](LAB_BOOK.md) for why things are the way they are** — every
measurement, decision and dead end is recorded there.

## What a fresh install gets, and how updates reach people

Everything needed to run is shipped **inside the app bundle** and written out on
first launch:

| Layer | What it is | Where it comes from |
|---|---|---|
| Pipeline | `nanohunter_run.sh` and its helper scripts | vendored from NanoHunter by `tools/sync_pipeline.sh` |
| Studio helpers | prediction batching, ligand analysis, campaign preparation | written here |
| RFdiffusion3 overlay | the whole RFD3 script layer — campaign orchestrators, ligand preparation, predictor adapters, length binning | vendored by `tools/sync_rfd3.sh` |

The last one matters more than it sounds: **none of it is upstream**. A clean
clone of the RFdiffusion3 MLX port contains zero of those scripts, so without the
overlay a new user gets a checkout that cannot run anything. The installer
applies it straight after cloning, before RFdiffusion3's own installer runs —
which is necessary, because that installer calls scripts the overlay provides.

The heavy parts — Python environments and model weights — are downloaded by
`setup_pipeline.sh` on first run. Source revisions, critical package versions,
and downloaded checkpoint hashes are pinned; an incomplete or changed artifact
fails setup. Existing NanoHunter/RFD3 installations can be linked explicitly,
then materialised into real local copies when a fully standalone root is wanted.

**Updates.** Push a change here and users get it the next time they launch a new
build: the bundled scripts are re-staged on every launch, and the overlay is
version-stamped so it is rewritten whenever the bundle differs from what is
installed. Environments and weights are *not* touched — they rarely change, and
re-downloading gigabytes on every update would be indefensible. If a change needs
a new dependency or a new model, that is a setup step and the app says so rather
than silently working differently.

Nothing here auto-updates the app itself. There is no updater and no signing yet,
so a new build is a new build someone has to run.

## Working on this repo

Read [CLAUDE.md](CLAUDE.md) first. Any AI agent working here is required to
record what it did in the Lab Book, including what it did not test.

## Status

Alpha. Builds and runs. Not signed or notarised, and no campaign has yet been run
end to end through the app — see the Known gaps list at the top of
[LAB_BOOK.md](LAB_BOOK.md).
