---
entry: 0003
title: Refresh the vendored pipeline, add AlphaFold 3 and OpenFold-3, expose scheduling
date: 2026-08-10
author: claude-opus-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [predictors, performance, install, ui]
---

## Context

Follows [[0001-repository-genesis-and-audit]] Finding 1 and 2, and implements the
decisions recorded in [[0002-inherited-speed-lessons]]. Studio could only run
Boltz → IntelliFold, and the runner it shipped predated every optimisation in
0002, so the flags to do anything else did not exist in the vendored script.

## What was done

**Vendored pipeline refresh.** `tools/sync_pipeline.sh` copies the runner and its
helper scripts from a NanoHunter checkout and writes
`Resources/pipeline/PIPELINE_VERSION` recording upstream commit, date, line count
and SHA-256. The file list is derived from
`grep -oE '\$\{REPO_ROOT\}/[A-Za-z0-9_./-]+' nanohunter_run.sh`, so a runner that
starts reaching for a new helper produces a `MISSING upstream` error rather than
a runtime failure inside a campaign.

**Installer.** `setup_pipeline.sh` gained opt-in components
(`--with-openfold3`, `--with-alphafold3`, `--with-intellifold-jax`,
`--with-rfd3`), per-component `NHSTATE` reporting, a `--detect` mode, and
`--link-existing` / `--link-rfd3`.

**App.** New `Predictor` and `InstallComponent` models; `DesignRequest` gained
`designPredictor`, `postPredictors`, `postOnlyHits`, `speedMode` and
`resumeIfPossible`; `CommandBuilder` emits the corresponding flags;
`PipelineInstaller` parses `NHSTATE` into per-component availability; the setup
wizard and design form were rebuilt around all of it.

## Results

*Implementation entry — the performance numbers it acts on were measured
upstream and are recorded in [[0002-inherited-speed-lessons]]. Nothing new was
benchmarked here.*

Two things were verified rather than assumed:

| Check | Result |
|---|---|
| Vendored runner line count, before → after | 5,823 → 7,073 |
| `--detect` on an empty root | all eight components correctly reported `missing` |
| `--link-existing` + `--link-rfd3` against this machine's checkouts | all eight reported `ok`, including AlphaFold 3 *with weights* and the IntelliFold JAX flash model |
| `swift build` / `./build_app.sh` | clean |

The link path is worth stating plainly: linking took under a second and detected
a complete installation, against roughly an hour and tens of gigabytes to install
from scratch.

## Decision and rationale

**The flags Studio does *not* pass matter as much as the ones it does.**
`--intellifold-buckets` and `--alphafold3-buckets` default to `auto`, which
resolves to the exact campaign token count — the single largest measured win
available (2.28× IntelliFold, 1.58× AF3). Passing an explicit bucket list from
the app would silently undo it. Likewise the per-predictor thread limits, which
already default correctly (1 for IntelliFold, untouched for Boltz, where the
same setting was measured *worse*). These are documented in `CommandBuilder` so
that a future agent adding "explicit is better than implicit" flags understands
what they would be breaking.

**Scheduling is delegated, not reimplemented.** `--throughput-profile auto` finds
the newest *compatible* device profile and rejects a machine/package/model/runner
fingerprint mismatch rather than reusing another Mac's settings. Rebuilding that
in Swift would create a second source of truth that could drift from the one that
was actually validated. Rejected alternative: a single "speed slider" mapping to
one global process count — meaningless when the measured optimum ranges from one
process (Boltz) to four (IntelliFold).

**Batched scheduling is offered but not the default.** Cycle-wave is where AF3 and
IntelliFold win most, but upstream explicitly has not validated it for ligand or
potentials workloads. It is therefore a labelled experimental choice rather than
a silent default, and the UI says why.

**The IntelliFold JAX backend is installable but not selectable.** `INTELLIFOLD_VENV`
and `INTELLIFOLD_RUNNER` are assigned unconditionally at `nanohunter_run.sh:63`
and `:100` — no `${VAR:-default}` — so there is **no supported route to the JAX
backend through the runner**. The 1.24× figure in 0002 came from a separate
benchmark harness. `--with-intellifold-jax` therefore prepares the environment
and converts the checkpoint, but the design form cannot yet offer it. Making it
selectable is upstream NanoHunter work, not Studio work.

**Post-prediction is framed as "checking", not as an optional extra.** The design
loop optimises sequences against whichever predictor drives it, so that
predictor's own iPTM is self-scored and is precisely the quantity most at risk of
being gamed — consistent with Boltz-2 + potentials scoring both highest and
tightest in the campaign table. The form pre-selects an orthogonal checker and
warns if the user removes them all.

**AlphaFold 3 weights are never fetched.** `af3.bin` is governed by Google's
terms. The installer reports `missing` with the exact path to place it, and
treats that as a normal state rather than a failure — the environment is still
usable, it just has nothing to run yet.

## Reproduce

```bash
cd /Users/thomasfryer/NanoHunterStudio
./tools/sync_pipeline.sh /Users/thomasfryer/NanoHunter
cat Sources/NanoHunterStudio/Resources/pipeline/PIPELINE_VERSION

# Detect / link, against a scratch root so nothing real is touched
export SCRATCH=$(mktemp -d)
cp Sources/NanoHunterStudio/Resources/pipeline/setup_pipeline.sh "$SCRATCH/"
NANOHUNTER_ROOT="$SCRATCH" bash "$SCRATCH/setup_pipeline.sh" --detect
NANOHUNTER_ROOT="$SCRATCH" bash "$SCRATCH/setup_pipeline.sh" \
  --link-existing /Users/thomasfryer/NanoHunter --link-rfd3 /Users/thomasfryer/RFD3

swift build && ./build_app.sh
```

## Limits and what was not tested

- **No campaign was run through the app.** The command construction, install
  detection and linking were exercised; an end-to-end design run with AlphaFold 3
  or OpenFold-3 as the design predictor was not. The flags match the runner's
  documented CLI, but that is an argument, not a test.
- The vendored-vs-upstream comparison is by line count and SHA, not a reviewed
  diff. The 1,250-line delta was not read hunk by hunk.
- `PIPELINE_VERSION` currently records the upstream tree as **dirty**, so the
  vendored copy does not correspond to any single upstream commit. That is
  recorded honestly rather than hidden, but it means exact reproduction needs
  the NanoHunter working tree as it stood on 2026-08-10.
- The time estimate shown in the form extrapolates from a 96-aa SUMO benchmark
  and ignores MSA generation and inverse folding entirely. It is labelled
  "at least" for that reason and should not be trusted within a factor of two.
- Symlinking `venvs/`, `src/` and `models/` to an existing checkout means an
  upgrade to NanoHunter changes Studio's behaviour without Studio changing. That
  is intended on a development machine and wrong for a distributed build; the
  vendored runner is still pinned, but the environments are not.

## Next

- Run a full campaign through the app on each of the four design predictors and
  record real wall times — Studio still has no measurements of its own.
- Make the IntelliFold JAX backend reachable: the smallest useful upstream change
  is to make `INTELLIFOLD_VENV` and `INTELLIFOLD_RUNNER` env-overridable.
- Trace the OpenFold-3 complex-pLDDT scale problem ([[0002-inherited-speed-lessons]] §7)
  and then surface that metric.
- Replicate the JAX `p1 × dir4` configuration (n=1 upstream); if 9.34 s at
  6.7 GiB holds, it is the right default for any Mac with less than 64 GB.
