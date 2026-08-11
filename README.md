# NanoHunter Studio

A native macOS app for designing nanobodies against your target — with a
guided setup, a clean design form, and a **live dashboard** that shows your
design metrics updating in real time and the 3D structures of every hit.

Built for people who want to design binders without touching a terminal.

![status](https://img.shields.io/badge/status-alpha-orange)

## What it does

1. **One-click setup** — installs the design engines (Boltz, IntelliFold,
   AntiFold, and the MPNN designers incl. AbMPNN) and their model weights behind
   a friendly progress screen. One time, no terminal.
2. **Guided design** — paste your target sequence, pick a validated nanobody
   scaffold, choose which CDR loops to redesign, set how many designs and your
   hit threshold. Sensible defaults throughout.
3. **Live dashboard** — watch iPTM climb per cycle across all runs, see the
   running hit count (iPTM ≥ your threshold, default 0.70), and inspect the 3D
   structure of every hit as it appears.

Default pipeline: **Boltz** design → **IntelliFold** prediction, with automatic
parallelization across your Mac's cores.

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

To work on it in Xcode, just `open Package.swift`.

## How it works

NanoHunter Studio is a friendly front end over the NanoHunter pipeline. It
vendors the pipeline scripts inside the app, installs the heavy dependencies
into `~/Library/Application Support/NanoHunterStudio/`, and drives
`nanohunter_run.sh` as a subprocess — parsing its per-cycle output to power the
live charts and the hits structure gallery.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

## Status

Alpha foundation. Working: setup wizard, project management, design form, live
metrics + hits gallery + structure viewer, run orchestration. For public
distribution the app still needs an icon and Developer ID notarization (open in
Xcode to archive).
