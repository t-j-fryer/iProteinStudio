---
entry: 0008
title: Self-contained installation, OpenFold-3 and the IntelliFold JAX backend
date: 2026-08-11
author: claude-opus-5
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [install, predictors, openfold, intellifold, reproducibility]
---

## Context

Three asks: stop refusing to wire OpenFold-3 and work out its input builders from
the runner; set up the IntelliFold JAX backend; and make the installation real —
everything installed here rather than symlinked elsewhere, as a first-time user
would get it.

## Results

### The install path was fundamentally broken, and had never been exercised

The single most important finding. The managed root was
`~/Library/Application Support/NanoHunterStudio`. That path contains a space, and
**a shebang line cannot contain a space** — the kernel splits on whitespace:

```
$ .../Application Support/NanoHunterStudio/venvs/NanoHunter_alphafold3/bin/intellifold
bad interpreter: /Users/thomasfryer/Library/Application: no such file or directory
```

Every console script pip creates in a venv carries an absolute shebang. So a
genuine from-scratch install into that directory would have produced a broken
`boltz`, `intellifold`, `run_openfold` — everything. It had never shown up
because on this machine the venvs were *symlinked* to a space-free path, so the
shebangs pointed there. The "install" path was never real.

The runtime now lives at `~/.nanohunterstudio`, the app migrates an old
installation automatically, and the installer **refuses** a path containing a
space rather than producing a subtly broken environment.

### Making the installation self-contained took three passes

Copying the directories is the easy part. Each pass found a way the copy was
still tied to the original:

1. **Console-script shebangs.** Rewrote line 1 — fixed `intellifold` and
   `run_openfold`, but not `boltz`, which uses a two-line `/bin/sh` + `exec`
   wrapper with the path on line 2. Now the old root is replaced wherever it
   appears in a wrapper.
2. **`activate` / `activate.csh` / `activate.fish`.** These start with `# `, not
   `#!`, so a "text wrapper" filter skipped them — and the runner *sources*
   `activate`, so a stale one silently re-points `VIRTUAL_ENV` and `PATH` back at
   the original installation. Included explicitly now.
3. **Editable installs.** `pip install -e` records the source directory as an
   absolute path in `site-packages`. After the copy, `import openfold3` still
   resolved to `/Users/thomasfryer/NanoHunter/src/openfold-3-mlx`. The
   installation looked self-contained and was not — and would have broken the
   moment the original was deleted.

Verified afterwards: zero references to the old location in any `bin/` or
`pyvenv.cfg`, `openfold3` and `intellifold` import from
`~/.nanohunterstudio/src/…`, and every console script runs.

| | |
|---|---|
| Components materialised | 9 |
| Symlinks remaining | 0 |
| Installation size | 16 GB |
| Components reporting `ok` | 9 / 9 |

RFdiffusion3 is copied without `campaigns/`, `.git`, cached fixtures, benchmarks
or figures — those are the user's results, not part of an installation, and
would have added several GB.

### OpenFold-3 — extracted rather than transcribed

The previous refusal was about transcribing ~130 lines blind. The answer was to
not transcribe at all: the builders were **extracted programmatically** from
`nanohunter_run.sh` into `scripts/openfold_query_json.py` and
`scripts/openfold_runner_yaml.py`, then checked against the originals.

| Builder | Check |
|---|---|
| query JSON | ran the runner's own function and the extracted script on the same input — **byte-identical** |
| runner YAML | GPU and CPU variants both **byte-identical** |

`RFD3/scripts/openfold_predict_one.py` calls those, runs `run_openfold`, and
normalises the seed-directory output to the `model_0.cif` + confidence contract.
OpenFold-3 is now selectable as an RFdiffusion3 checker.

One bug found by running it: the adapter passed no binder MSA, so the builder
fell back to the MSA server for chain A — slow, wrong for a de-novo binder, and
fatal when the server is down. Fixed; the query JSON now carries the supplied MSA.

### IntelliFold JAX — working, and measured

This is the ~1.24× that three previous entries recorded as unavailable. The
obstacle was that the JAX backend reuses AlphaFold 3's engine and therefore reads
**AF3 fold-input JSON**, not NanoHunter YAML. NanoHunter's own
`alphafold3_adapter.py` already converts in both directions, so
`intellifold_jax_predict_one.py` uses it for input *and* output normalisation —
no new conversion logic.

Run end to end from the app's own installation:

```
{"ptm": 0.47, "complex_plddt": 0.760, "predictor": "intellifold-jax", ...}
model inference with seed 42 took 30.66 seconds
```

The adapter is AF3's, so it stamped `"predictor": "alphafold3"` on the metrics.
These predictions come from IntelliFold's weights on AF3's engine; leaving that
label would have credited the wrong model in every downstream table. Overridden
in both the returned metrics and `confidence.json`.

It is exposed as a separate engine rather than a setting, because it is a
different implementation: it needs roughly twice the memory and its outputs are
close to, but not identical to, the PyTorch backend's.

## Decision and rationale

**A space-free runtime root, not a workaround.** The polyglot `#!/bin/sh` + exec
trick can make a single script survive a spaced path, but every future `pip
install` would write a fresh broken shebang. Moving the root fixes the class.

**Editable installs are re-pointed, not reinstalled.** Reinstalling would be
cleaner in principle and would have meant recompiling AlphaFold 3 from source.
Re-pointing is verified by importing the packages and checking where they resolve.

**RFdiffusion3 is copied, not re-cloned, when materialising.** A fresh clone
would lose local changes — including the adapters this work added. The installer
*does* clone when nothing is present, so a first-time install still works.

**IntelliFold JAX is not offered in the iterative tab.** `nanohunter_run.sh`
hard-assigns IntelliFold's environment and runner, so there is still no route
there. It is offered in the RFdiffusion3 checker, which calls adapters directly.

## Reproduce

```bash
NEW="$HOME/.nanohunterstudio"
NANOHUNTER_ROOT="$NEW" bash "$NEW/setup_pipeline.sh" --detect
NANOHUNTER_ROOT="$NEW" bash "$NEW/setup_pipeline.sh" --materialise   # links -> real copies
NANOHUNTER_ROOT="$NEW" bash "$NEW/setup_pipeline.sh" --repair-venvs  # re-point after a move

# Byte-identity of the extracted OpenFold builders (from a NanoHunter checkout)
cd /Users/thomasfryer/NanoHunter
python3 scripts/openfold_query_json.py TEMPLATE.yaml BINDERSEQ demo /tmp/new.json MSA ""
# compare against the runner's own build_openfold_query_json on the same input

# The JAX backend, end to end
cd "$NEW/rfd3"
"$NEW/venvs/NanoHunter_alphafold3/bin/python" scripts/intellifold_jax_predict_one.py \
  --yaml tiny.yaml --output /tmp/out --nanohunter-root "$NEW"
```

## Limits and what was not tested

- **A true from-scratch install was not run.** The installation was
  *materialised* from symlinks, not built from nothing. The new install path
  (including the LASErMPNN component and the RFD3 clone) is written but unproven;
  the space guard means it can no longer fail the old way, which is the failure
  that mattered.
- **OpenFold-3 has not produced a structure.** Its plumbing is proven — query
  JSON built with the right MSA, runner YAML written, CLI launched, model loaded
  — but the run failed inside OpenFold parsing a hand-made single-sequence A3M
  (`IndexError` in `msa.py:937`, `all_msas_per_chain` empty). That looks like a
  malformed test input rather than an adapter fault, but it is unproven either
  way. **The first real OpenFold-3 check may fail.**
- The IntelliFold JAX test was one 42-residue monomer. No complex, no ligand, no
  concurrency, and no timing claim beyond the 30.7 s that run took — which is not
  comparable to the 9.15 s benchmark figure (different workload, and the
  compilation cache was cold).
- `NanoHunter_intellifold`'s venv cannot `import intellifold` after the copy,
  where the original can. The runner invokes it by script path and that was
  verified working, so this is cosmetic — but it is a difference I did not
  resolve.
- Venv relocation was verified on this machine's layout only. A venv built by
  `uv` versus `python -m venv` differs in how much absolute path it embeds.

## Next

1. Run a real from-scratch install into an empty root and fix whatever it reveals.
   Everything else in this entry is downstream of that being trustworthy.
2. Get one OpenFold-3 prediction to complete on a realistic input.
3. Studio still has no measurements of its own. Five entries running.
