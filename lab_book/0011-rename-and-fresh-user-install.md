---
entry: 0011
title: Rename to iProteinStudio, per-engine installs, and a clean-clone check
date: 2026-08-13
author: claude-opus-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [install, reproducibility, rename, docs, ui]
---

## Context

Four asks: let people install engines individually rather than all-or-nothing,
make that revisable inside the app, prompt for AlphaFold 3 weights, document the
CLI and give AI agents instructions — then rename everything to iProteinStudio
and check the repo as a new user would receive it.

## Results

### Local paths were shipped in nine scripts

`git grep /Users/thomasfryer` over the shipped tree found real defects, not
cosmetics:

| What | Effect on a new user |
|---|---|
| Nine RFD3 scripts with `--nanohunter-root` defaulting to `/Users/thomasfryer/NanoHunter` | every one silently pointed at a directory that does not exist |
| `prepare_acbx_target.py` defaulting to one campaign's output | unusable |
| Generated ligand manifests recording absolute paths | one machine's layout inside every install |
| Provenance stamps recording the developer's directory | not harmful, just wrong |

Fixed at source in the RFD3 checkout, then re-vendored — the first attempt fixed
the vendored copies and was immediately overwritten by the next `sync_rfd3.sh`
run, which is the argument for fixing upstream rather than downstream.

Roots now come from `NANOHUNTER_ROOT`, falling back to the script's own location
**with a check**: if there is no `venvs/` above it, it raises rather than
silently using a home directory.

### Installation became a real choice

Every engine is individually selectable, with size and consequence stated:

| Engine | Size | Without it |
|---|---|---|
| Sequence designers | ~500 MB | always installed |
| Boltz-2 | ~4 GB | no default folding, no affinity, no alignment generation |
| AntiFold | ~2 GB | no nanobody CDR design |
| IntelliFold | ~3 GB | no second opinion |
| IntelliFold JAX | shares AF3 env | no faster IntelliFold |
| OpenFold-3 | ~4 GB | one fewer independent check |
| AlphaFold 3 | ~3 GB + own weights | no AF3 |
| LASErMPNN | ~2 GB | no ligand-aware side-chain design |
| RFdiffusion3 | ~5 GB | no RFdiffusion3 tab |

Dependencies are pulled in automatically — selecting the JAX backend brings the
AlphaFold 3 environment, selecting RFdiffusion3 brings Boltz — so a user cannot
choose something that then fails for a missing prerequisite. An Engines sheet in
the toolbar makes all of it revisable later.

**AlphaFold 3 weights** are the one thing the app cannot fetch. It now detects
"environment present, weights absent", opens the sheet on launch, and copies the
chosen file rather than referencing it — the file is usually picked from
Downloads, and a campaign failing three days in because it moved is a bad way to
find out. A file too small to be the parameter set is rejected immediately.

### Two bugs the rename exposed

Moving `~/.nanohunterstudio` to `~/.iproteinstudio` broke IntelliFold and
OpenFold-3, because `--repair-venvs` re-pointed shebangs and `activate` scripts
but **not editable installs** — whose absolute source path lives in a `.pth` and
a generated `__editable___*_finder.py`.

Worse, the shell implementation of that repair **failed silently**: it found the
stale root correctly when run by hand, rewrote nothing, and reported success.
That is exactly the failure mode the function exists to prevent. Reimplemented in
Python, where the logic can be read. After: all engines run, zero stale pointers.

### Clean-clone check

Cloned from GitHub into an empty directory as a new user would:

| Check | Result |
|---|---|
| Repository size | 12 MB |
| Weights or model files committed | none |
| Local paths outside the Lab Book | none |
| `./build_app.sh` from scratch | succeeds, 2 min 11 s |
| Bundle contents | 7,073-line runner, 12 pipeline scripts, 7 Studio helpers, 27 RFD3 overlay scripts, installer |
| `--detect` on an empty root | all nine components correctly `missing` |
| All nine engine flags | accepted |
| Path containing a space | refused with the reason |

The Lab Book keeps its absolute paths. Entries record what was true when written,
and rewriting them to match a rename would falsify the history they exist to
preserve. `CLAUDE.md` was de-localised, because it is an instruction file — an
agent reading it on a fresh clone would otherwise hunt for sibling repos that are
neither present nor needed.

## Decision and rationale

**Only the sequence designers are unconditional.** Every prediction engine is a
free choice. They are gigabytes each, nobody needs all of them, and the previous
"core four" was an assumption about workflow rather than a requirement.

**Copy the AlphaFold 3 weights, do not reference them.** A path into Downloads is
a time bomb.

**Rename the runtime root, with a migration chain.** Three historical locations
(`Application Support/NanoHunterStudio`, `Application Support/iProteinStudio`,
`~/.nanohunterstudio`) all migrate to `~/.iproteinstudio`. A rename that stranded
16 GB would be a poor trade for a tidier name.

**Keep the venv prefix `NanoHunter_*`.** It is the upstream pipeline's naming and
the runner derives paths from it; renaming would break the runner for no user
benefit.

Rejected: rewriting the Lab Book. Rejected: a shell fix for the editable-install
repair — it had already failed silently once.

## Reproduce

```bash
git clone https://github.com/t-j-fryer/iProteinStudio.git && cd iProteinStudio
./build_app.sh
grep -rn "/Users/" . --exclude-dir=.git | grep -v lab_book   # expect nothing

ROOT=/tmp/fresh_root && mkdir -p "$ROOT"
cp build/iProteinStudio.app/Contents/Resources/*.bundle/pipeline/setup_pipeline.sh "$ROOT/"
NANOHUNTER_ROOT="$ROOT" bash "$ROOT/setup_pipeline.sh" --detect
```

## Limits and what was not tested

- **A full fresh install still has not been run.** `--detect` works on an empty
  root, all flags are accepted, the space guard fires, and the bundle is
  complete — but no engine has been downloaded and installed from nothing. This
  has been the top open item for three entries. It needs a machine, or several
  hours and tens of gigabytes, and it is the last thing standing between this and
  a defensible claim of reproducibility.
- The Engines sheet and the AlphaFold 3 weights prompt have not been clicked. The
  copy-and-validate logic is straightforward but unexercised.
- The per-engine install branches (`--with-boltz` and friends) were verified to
  *parse* and to be accepted; none has actually installed anything in isolation.
  In particular an install of only, say, OpenFold-3 — with no Boltz to generate
  alignments — has never been tried and may not be a coherent configuration.
- The rename was checked by grep and by building. No saved project from before
  the rename has been opened in the renamed app.

## Next

1. Fresh install on a clean machine. Everything else is downstream of it.
2. Check that a project saved before the rename still loads.
3. Try a deliberately minimal install (one engine) and see whether the app
   degrades sensibly or assumes Boltz.
