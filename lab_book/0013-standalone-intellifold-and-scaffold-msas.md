---
entry: 0013
title: A standalone install with both IntelliFold v2 models and bundled nanobody MSAs
date: 2026-08-13
author: codex-gpt-5
type: port
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [install, reproducibility, intellifold, jax, nanobody, msa, rfd3]
---

## Context

Entry 0012 started a from-scratch install, but an engine reporting `ok` still
meant only that selected files existed. The app could borrow Boltz and
IntelliFold data from home-directory caches, RFdiffusion3's overlay still called
helpers from the NanoHunter checkout, only IntelliFold v2-flash was selectable,
and the seven scaffold YAMLs shipped without their deep MSAs. A clone could
therefore look complete on this development Mac and fail for a new user.

This pass inspected `/Users/thomasfryer/NanoHunter` for the validated
IntelliFold JAX v2-flash work and treated a separate managed root,
`/Users/thomasfryer/.iproteinstudio_freshtest`, as the acceptance environment.

## What was done

- Pinned every cloned engine to an exact revision and pinned critical package
  versions. Model and data downloads are atomic and checked by SHA-256. Missing
  or changed artifacts fail instead of silently selecting another model.
- Moved Boltz models/CCD data, its writable Numba cache, IntelliFold PyTorch
  checkpoints/CCD data, both JAX model variants, and OpenFold's checkpoint under
  the managed root. The runners receive those paths explicitly.
- Bundled the exact NanoHunter IntelliFold patch against its pinned upstream
  base. Full v2 uses IntelliFold's upstream JAX weights; v2-flash is converted
  reproducibly from the verified PyTorch checkpoint and uses NanoHunter's
  smaller graph/conditioning patch.
- Added one `v2-flash`/`v2` selector and carried it through iterative design,
  target preparation, the prediction tab, and RFdiffusion3 verification for
  both PyTorch and JAX. Old saved requests decode to v2-flash. The UI suppresses
  time/speed claims for full v2 because it has no recorded benchmark.
- Copied the seven validated scaffold A3Ms from NanoHunter into the app bundle
  and seed them into the persistent scaffold cache on launch without
  overwriting a generated/user copy.
- Removed the RFD3 overlay's runtime import of NanoHunter's NISE library. The
  generic process, YAML, ranking and coordinate helpers are now in
  `studio_runtime.py`; the LASErMPNN invocation is an exact port of the
  validated call. NISE itself remains out of Studio.
- Made prediction batches and RFdiffusion3 checks propagate failures. Fixed the
  RFD3 exported-weight hash so it is reproducible: its tensors were identical,
  but the safetensors metadata embedded the absolute install path. The exporter
  now records only the pinned checkpoint filename, and the check command now
  exits non-zero on a mismatch.
- Changed first-run defaults to install Boltz, AntiFold and IntelliFold alongside
  the unconditional MPNN environment. Setup completion is keyed to that true
  unconditional core, rather than wrongly requiring optional Boltz.

## Results

These are acceptance observations, not comparative benchmarks. Each inference
condition was run once on one 71-residue α-cobratoxin monomer. Caches were warm.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Complete managed root except legally gated AF3 parameters | 1 | disk use (`du -sh`) | 28 GB |
| Boltz-2, shipped 1,148-record MSA, MSA server disabled | 1 | batch completion | 1/1 in 21.1 s |
| IntelliFold JAX v2-flash through prediction batch | 1 | completion / emitted model tag | 1/1 in 26.1 s / `v2-flash` |
| IntelliFold JAX full v2 through prediction batch | 1 | completion / emitted model tag | 1/1 in 99.4 s / `v2` |
| IntelliFold PyTorch v2-flash direct acceptance | 1 | completed inference | 78.37 s |
| IntelliFold PyTorch full v2 direct acceptance | 1 | completed inference | 427.99 s |
| LASErMPNN, one 115-residue biotin-containing backbone | 1 | sequences / wall time | 1 / 3.42 s |
| RFdiffusion3 exported MLX weight, two consecutive exports | 2 | SHA-256 | `0beb87ff872d946a8af58428ae7c679eb364057bf12df77dba5994f6a0f1271b` both times |

The final detector reported Boltz, MPNN, AntiFold, IntelliFold PyTorch,
OpenFold-3, LASErMPNN, IntelliFold JAX and RFdiffusion3 `ok`. AlphaFold 3
reported `missing` only because `af3.bin` is not redistributable; its environment
was present. RFdiffusion3's own check passed MLX Metal, PyTorch MPS, the FHE CCD,
the official checkpoint hash and the deterministic exported-weight hash.

All seven alignment queries exactly match both the catalog sequence and the
sequence embedded in the scaffold YAML. They are byte-identical to NanoHunter:

| Scaffold | A3M records |
|---|---:|
| `7xl0_vobarilizumab` | 12,014 |
| `7eow_caplacizumab` | 11,514 |
| `8coh_gefurulimab` | 11,766 |
| `8z8v_ozoralizumab_alb8` | 12,594 |
| `gontivimab` | 10,393 |
| `isecarosmab` | 11,705 |
| `sonelokimab` | 11,591 |

`swift build` passed, the release app assembled with `build_app.sh`, and the
resulting 25 MB bundle contains all seven A3Ms, the IntelliFold patch and the
self-contained RFD3 runtime. Every shell script passed `bash -n`, every Python
file compiled, every Swift file passed frontend parsing, and `git diff --check`
passed.

## Decision and rationale

**Managed copies are the default; links are an explicit optimisation.** A
developer checkout is convenient but is not evidence a GitHub user can install.
The app may link an existing installation when asked, and can materialise it,
but the normal path downloads pinned inputs beneath `~/.iproteinstudio`.

**Both IntelliFold architectures are explicit.** Substituting v2-flash when v2
is missing (or vice versa) would make an experiment irreproducible. Separate
files/directories and a serialized model choice make the selected network part
of the run record.

**Ship the scaffold MSAs.** Roughly 11 MB in Git turns the seven advertised
scaffolds into offline, reproducible inputs. Requiring every first-time user to
regenerate identical alignments is slower, network-dependent, and inconsistent
with shipping the scaffold sequences themselves.

**Port generic validated behaviour, not NISE.** Studio needs the established
LASErMPNN and ranking calls, but not NanoHunter's experimental NISE campaign.
Keeping the small generic runtime in this repository satisfies the standalone
contract without expanding product scope.

## Reproduce

```bash
cd /Users/thomasfryer/NanoHunterStudio
FRESH=/Users/thomasfryer/.iproteinstudio_freshtest

# Final integrity/detection pass.
NANOHUNTER_ROOT="$FRESH" bash "$FRESH/setup_pipeline.sh" --detect
NANOHUNTER_ROOT="$FRESH" "$FRESH/rfd3/install_rfd3.sh" --check

# Offline Boltz batch; the JSON names the bundled aCbx MSA and allow_server=false.
"$FRESH/venvs/NanoHunter_boltz/bin/python" \
  "$FRESH/rfd3_scripts/predict_batch.py" \
  --config /private/tmp/iproteinstudio-fresh-acbx.json

# The same batch route for IntelliFold JAX; set intellifold_model in the JSON
# first to v2-flash, then v2. Both outputs record the selected model.
"$FRESH/venvs/NanoHunter_boltz/bin/python" \
  "$FRESH/rfd3_scripts/predict_batch.py" \
  --config /private/tmp/iproteinstudio-jax-batch.json

# PyTorch architecture checks use the exact managed cache.
"$FRESH/venvs/NanoHunter_intellifold/bin/python" \
  "$FRESH/src/IntelliFold/run_intellifold.py" \
  /private/tmp/iproteinstudio-fresh-acbx-output/inputs/acbx_fresh_install.yaml \
  --out_dir /private/tmp/iproteinstudio-pytorch-v2 --precision no \
  --num_workers 0 --seed 42 --num_diffusion_samples 1 --override \
  --model v2 --cache "$FRESH/models/intellifold"

# LASErMPNN with the ligand matching the input PDB.
"$FRESH/rfd3/.venv/bin/python" "$FRESH/rfd3/scripts/run_lasermpnn.py" \
  --backbones /private/tmp/iproteinstudio-lasermpnn-input \
  --output /private/tmp/iproteinstudio-lasermpnn-output-biotin \
  --smiles 'O=C(O)CCCCC1SCC2NC(=O)NC21' --n-seqs 1 --max-parallel 1 \
  --nanohunter-root "$FRESH" --seq-temp 0.5 --fs-temp 0.7 \
  --fs-distance 10 --ala-budget 2 --gly-budget 0 --no-constrain-ss

swift build
./build_app.sh
```

## Limits and what was not tested

- The Python/package caches on this Mac were warm. This exercises installation
  into an empty managed root, not every cold network download on a second Mac.
- The IntelliFold runs were a single short monomer. No multimer, antibody–target
  complex or ligand case was used, and the timings above must not be generalized
  into model-speed claims.
- AntiFold and OpenFold-3 passed install/import/checkpoint detection but did not
  run an inference in this pass.
- AlphaFold 3 inference was not run because the isolated root intentionally has
  no user-supplied `af3.bin`.
- RFdiffusion3's environment, Metal access, chemical component and weights
  passed its self-check; no backbone was generated and no full RFD3 campaign was
  run.
- The app compiled and its resources were inspected, but the setup/model picker
  was not clicked in the GUI. The selector's Python routes were exercised via
  the same serialized configs the controllers write.
- LASErMPNN itself has no seed argument, so that design stage is resumable and
  counted but not bit-reproducible across a forced rerun.

## Next

1. Run one small nanobody campaign by clicking through the release app, using a
   bundled scaffold/MSA and each IntelliFold choice.
2. Run a minimal RFdiffusion3 protein campaign through backbone generation,
   sequence design, verification and ranking.
3. Repeat setup on a genuinely clean second Apple-Silicon Mac with a cold
   package/download cache.
