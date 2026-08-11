# NanoHunter Studio

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

**One-click setup** — installs the design engines and their weights behind a
friendly progress screen. If you already have NanoHunter installed, Studio links
to it in about a second instead of downloading tens of gigabytes again.

## Engines

| | |
|---|---|
| Structure prediction | Boltz-2 (± steering potentials), IntelliFold, AlphaFold 3, OpenFold-3 |
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
open "build/NanoHunter Studio.app"
```

Or during development:

```bash
swift build && swift run
```

To work on it in Xcode, `open Package.swift`.

## How it works

Studio is a front end. The science lives in sibling repositories — **NanoHunter**
for iterative design and prediction, **RFD3** for RFdiffusion3 — and Studio drives
their validated scripts rather than reimplementing them. It vendors the NanoHunter
pipeline into its bundle (see `tools/sync_pipeline.sh` and
`Resources/pipeline/PIPELINE_VERSION` for exactly which version), installs into
`~/Library/Application Support/NanoHunterStudio/`, and parses the runners' output
to drive the live views.

RFdiffusion3 campaigns can run for days, so they are launched detached and keep
going if you quit the app; reopening the project reattaches to the running
campaign.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design, and
**[LAB_BOOK.md](LAB_BOOK.md) for why things are the way they are** — every
measurement, decision and dead end is recorded there.

## Working on this repo

Read [CLAUDE.md](CLAUDE.md) first. Any AI agent working here is required to
record what it did in the Lab Book, including what it did not test.

## Status

Alpha. Builds and runs. Not signed or notarised, and no campaign has yet been run
end to end through the app — see the Known gaps list at the top of
[LAB_BOOK.md](LAB_BOOK.md).
