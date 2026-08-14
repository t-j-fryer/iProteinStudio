---
entry: 0015
title: Exercise real GUI GPU jobs and audit the app as a product
date: 2026-08-14
author: codex-gpt-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, accessibility, gpu, prediction, iterative-design, rfd3]
---

## Context

Entry [[0014-runtime-promotion-and-persistent-navigation]] promoted the clean,
standalone install to `~/.iproteinstudio` and made the workflow selector remain
visible during long runs. Its acceptance work deliberately stopped short of a
real GUI campaign. This pass exercised the built app against that promoted
runtime, confirmed the actual Apple-GPU processes it launches, and reviewed the
interface as a product for a bench scientist rather than only as working code.

## What was done

- Ran the saved 71-residue alpha-cobratoxin prediction from the built GUI with
  Boltz and AlphaFold 3 selected. While it was active, switched between Predict,
  Iterative design and RFdiffusion3; the selector remained enabled, the active
  banner remained visible, and RFdiffusion3's Start button was disabled with a
  plain-language explanation.
- Found and fixed a real AlphaFold 3 / IntelliFold JAX launch bug. A FASTA title
  beginning with Greek alpha became `-Cobratoxin`; passing that as a separate
  value after `--name` made `argparse` treat it as an option. Every affected
  Python and shell route now uses `--name=<value>`.
- Prevented ASCII-safe job names from retaining leading/trailing `.`, `_` or
  `-`, so the same example now parses as `Cobratoxin` rather than
  `-Cobratoxin`.
- Re-ran AlphaFold 3 alone from the GUI after staging the repaired overlay and
  confirmed a successful MPS fold and normalized CIF output.
- Ran a one-design, one-cycle ligand mini-binder campaign from the GUI. The
  launch used LigandMPNN and Boltz with steering potentials, and the campaign
  completed with exit code 0. The project's prior 4-design/5-cycle settings
  were restored after the acceptance run.
- Prepared the bundled alpha-cobratoxin RFdiffusion3 protein request and ran a
  deliberately tiny one-backbone, 65-residue, 10-step acceptance job through
  the same staged `rfd3_protein_campaign.py` that the GUI launches. This
  exercised Foundry fixture preparation followed by the MLX backbone path.
- Found and fixed the RFdiffusion3 worked-example preset. It supplied the PDB
  and hotspots but not the sequence or full motif range, so it would later fail
  at target-MSA generation and could fall back to designing against only `B1`.
  It now records the 71-residue sequence and `B1-71`. The rebuilt GUI visibly
  showed the sequence, `target.pdb`, chain B and `Using residues B1-71`; the real
  preflight resolved B67, B69 and B71.
- Added explicit accessibility labels, hints and stable identifiers to worked
  examples and all three primary Start actions. Before this change,
  Accessibility inspection reported all four direct RFdiffusion3 buttons in
  the initial viewport only as generic `button` controls.
- Inspected and captured Iterative design, RFdiffusion3, Predict and Engines in
  the release GUI. This exposed product-level strengths and gaps recorded below.
- Ran long tests under `caffeinate -dimsu`. Without it, the GPU subprocesses
  continued but macOS reached the login screen and GUI automation lost access
  to the app window.

## Results

These are acceptance observations, not general performance benchmarks. Each
condition was run once on the M4 Max in the header.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Boltz monomer, 71 aa, Predict tab | 1 | structure inference shown by Boltz | 4 s |
| AlphaFold 3 monomer, 71 aa, bucket 128 | 1 | model inference, seed 42 | 28.90 s |
| AlphaFold 3 GUI batch | 1 | wall time, 1 result / 0 failures | 38.2 s |
| Iterative ligand design, 1 design × 1 optimisation cycle | 1 | recorded run wall time, exit 0 | 2,702.56 s |
| Iterative cycle 00 | 1 | recorded cycle time | 670.01 s |
| Iterative cycle 01 | 1 | recorded cycle time | 2,007.11 s |
| RFdiffusion3 protein fixture, 65-aa binder | 1 | Foundry fixture preparation | 456 s |
| RFdiffusion3 MLX, 65-aa binder, 10 steps, batch 1 | 1 | recorded batch wall time | 0.643 s |
| RFdiffusion3 MLX same job | 1 | end-to-end bin wall time | 0.977 s |

Boltz explicitly logged `GPU available: True (mps), used: True` in both the
prediction batch and iterative cycles. AlphaFold 3 logged `using device 0:
MPS:0`. The RFdiffusion3 environment reported `Device(gpu, 0)` and `Apple M4
Max`; it produced one PDB and a complete metrics row. The RFdiffusion3 PDB quota
check passed (expected 1, found 1).

The first mixed Boltz + AlphaFold 3 GUI run was useful failure evidence rather
than a success: Boltz completed, AlphaFold 3 rejected `--name -Cobratoxin`, and
the GUI correctly reported 1 of 2 failed. Its recorded batch wall time was
111.4 s. After the argument fix, the AF3-only rerun completed 1 of 1.

The Iterative output contains both cycle structures. iPTM changed from
0.8275057 at cycle 00 to 0.8614884 at cycle 01. Those values show that the files
and metrics route completed; this single acceptance run is not evidence that a
particular design strategy improves iPTM.

## Product assessment

### What already works well

- The app looks and behaves like a native modern macOS application. The dark
  material palette, restrained blue accent, consistent cards, typography and
  segmented workflow navigation form a coherent visual system.
- The three workflows use task language rather than implementation language.
  Examples, inline explanations, validation warnings, estimates and disabled
  states give a new user much more guidance than a thin GUI over shell scripts.
- The worked examples, molecule drawing, managed Engines sheet, explicit model
  choice and reusable alignment behavior make sophisticated local workflows
  discoverable without requiring a terminal.
- Status is not communicated by color alone in the Engines sheet: checkmarks
  and the word `installed` accompany green state.
- Mutual exclusion is correctly attached to starting GPU work, not to
  navigation. This is both safer and less confining.

### Highest-priority improvements

1. **Make run history and recovery first-class.** After restarting the app, the
   completed Iterative campaign remained on disk but the project returned to
   the setup form. A scientist should see prior runs, success/failure badges,
   their settings, outputs, and a clear Resume or Open Results action. This is
   the largest mismatch with the repository's resumability requirement.
2. **Use progressive disclosure and a sticky action bar.** All three forms are
   very long; the primary Start action can sit several screens below the target
   input. Keep Start, validation state and the estimate visible at the bottom,
   and offer Quick Run / Advanced modes or presets.
3. **Replace raw logs with actionable result and error cards.** Keep full logs
   available, but lead with the failed engine, a plain-language reason, the
   affected item, and `Retry failed model` / `Open log` actions. The current
   progress screens expose substantial Python/JAX/PyTorch noise.
4. **Complete the accessibility pass.** The primary controls fixed here were
   not the only generic AX elements. Add labels and identifiers throughout,
   verify keyboard focus order, VoiceOver, large text, reduced motion and
   contrast. Example cards should announce their purpose and hint, which this
   pass now does.
5. **Add a global activity centre.** Show the active workflow, stage, elapsed
   time and queued work from every project, with safe Stop and Reveal Output
   actions. GPU mutual exclusion then becomes obvious rather than an isolated
   disabled button.
6. **Polish distribution and lifecycle.** Add an app icon, Developer ID
   signing/notarisation, update delivery, disk-space estimates, runtime cleanup
   and a way to remove the retained pre-promotion backup after acceptance.

Secondary visual improvements: raise contrast for tertiary explanatory copy,
reduce repeated prose, avoid truncated project summaries in the narrow sidebar,
and add useful empty/loading/result imagery rather than leaving the user with a
form or raw log at every state.

## Decision and rationale

**Treat GPU launch evidence as process plus output, not a button click.** For
each engine, the audit captured the actual backend/device and required a result
or explicit failure. This caught the AF3 name bug that a launch-only check would
have missed.

**Keep the RFdiffusion3 acceptance job small and protein-only.** One backbone
with 10 diffusion steps proves the staged MLX route and avoids launching an
hours-long verification campaign during a UI audit. The small-molecule NISE
path remains deliberately out of Studio's acceptance scope.

**Fix functional and accessibility defects found during testing, but record the
larger redesign instead of attempting it incidentally.** Run history,
progressive disclosure and result presentation need coherent product design and
should not arrive as isolated patches hidden inside a GPU acceptance pass.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio

# Keep the Mac and display awake for interactive tests.
caffeinate -dimsu -t 7200

# Required source/build checks. Isolated caches avoid managed-shell cache denial.
bash -n Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh
PYTHONPYCACHEPREFIX=/private/tmp/iproteinstudio-pycache \
  python3 -m py_compile \
  Sources/iProteinStudio/Resources/rfd3_overlay/scripts/af3_predict_one.py \
  Sources/iProteinStudio/Resources/rfd3_overlay/scripts/intellifold_jax_predict_one.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swiftpm-cache \
  swift build

# Device confirmation used for the RFdiffusion3 acceptance output.
/Users/thomasfryer/.iproteinstudio/rfd3/.venv/bin/python -c \
  'import mlx.core as mx; print(mx.default_device()); print(mx.device_info()["device_name"])'

# Release bundle used for the GUI pass.
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swiftpm-cache \
  ./build_app.sh
open /Users/thomasfryer/iProteinStudio/build/iProteinStudio.app
```

The exact temporary RFdiffusion3 request and output were intentionally not
committed. Its generated config specified the shipped `examples/acbx/target.pdb`,
contig `65-65,/0,B1-71`, hotspots B67/B69/B71, one backbone, 10 steps, one
recycle, batch 1, queue 1 and bf16.

## Limits and what was not tested

- The RFdiffusion3 protein acceptance stopped after fixture and backbone
  generation. SolubleMPNN, target-MSA generation, complex verification and
  ranking were not run, and the tiny job was launched through the same staged
  runner as the GUI rather than by pressing the GUI Start button.
- No nanobody campaign was run from the GUI. The bundled scaffold/MSA acceptance
  matrix remains the evidence in entry 0013.
- IntelliFold PyTorch, IntelliFold JAX, OpenFold-3 and post-design AlphaFold 3
  checking were not repeated in an Iterative campaign.
- The first mixed prediction run failed before AF3 inference; the successful AF3
  rerun used AF3 alone. Boltz and AF3 both succeeded separately through the GUI.
- Timings are single acceptance observations on one machine under changing
  thermal/load conditions. In particular, the Iterative Boltz stages varied
  widely and must not replace controlled benchmarks.
- Accessibility was inspected through macOS AX and by screenshots, not through
  a complete VoiceOver task script or external users.
- Signing, notarisation, app icon, updater and a truly separate macOS user
  account were not tested.

## Next

1. Build a persistent per-project run-history/recovery view before launching
   more multi-hour acceptance campaigns.
2. Run the complete RFdiffusion3 protein path from the GUI with one backbone,
   one sequence and one verifier, then surface its result in the app.
3. Run a one-scaffold nanobody GUI acceptance campaign using its bundled MSA.
4. Perform a focused VoiceOver/keyboard pass and label every remaining generic
   interactive element.
