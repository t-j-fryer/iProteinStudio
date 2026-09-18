# Physical guidance without FK and early exposure checks

User-authorized follow-up to `biotin_guidance_replay_v1`. This experiment keeps
Boltz's physical and pocket/contact guidance, disables FK resampling, and sends
all 30 frozen inputs together to a resident model. One directory request means
sequential data-loader batches of one, not 30 simultaneously folded proteins.

The first arm measures clean request time. The second repeats the inputs with
read-only snapshots after diffusion step 1 and every 5 steps through 200. Both
the physically corrected denoised estimate and the noisy diffusion state are
saved. All predictions finish; there is no early termination.
Exposure is evaluated on the denoised estimates only. Early noisy states are
not molecular structures; applying FreeSASA to their huge coordinate extent
failed its spatial-grid allocation in the pilot. Those states remain archived
for provenance and final-coordinate equality, not treated as failed exposure.

`prepare.py` freezes the prior replay's preprocessed inputs and per-input RNG
states, snapshots the runner, and creates a broker plan. It never launches work.
Start its returned plan with `job_start` and the exact digest. A two-input pilot
must pass before the 30-input test. The first pilot completed but failed the
output audit because Lightning logged its initial FK-on settings despite the
sampler override; a fresh pilot records the override with `save_hyperparameters`.
The original outputs are retained. Both pilots are excluded from main timing.

```sh
NANOHUNTER_ROOT="$RUNTIME_ROOT" /usr/bin/python3 \
  Validation/experiments/biotin_single_particle_v1/prepare.py \
  --source-job job-1fdba14287be --limit 2 \
  --records Validation/output/biotin_single_particle_v1/pilot2
```

After broker completion, `analyse.py` validates the immutable inputs, completion
receipts, executed settings, one-request/model-load counts and MPS fallback
policy. It checks output sequence, coordinates, confidence and ligand atoms.
It compares geometry using the previous experiment's unchanged diagnostics,
including independent CIP and signed-volume stereochemistry checks.

Snapshots are converted using Boltz's own atom table and PDB writer. The final
snapshot must reproduce every emitted atom coordinate exactly before any early
exposure results are accepted. The unchanged production SASA filter checks O18
and O19 against the same 50% retained-accessibility threshold. Initializations
contain X residues; they are not completed, all-side-chain designs.

```sh
NANOHUNTER_ROOT="$RUNTIME_ROOT" NUMBA_CACHE_DIR="$TMPDIR/studio-numba" \
  "$RUNTIME_ROOT/venvs/NanoHunter_boltz/bin/python" \
  Validation/experiments/biotin_single_particle_v1/analyse.py \
  --output "$RUN_OUTPUT" --destination "$ANALYSIS_OUTPUT"
```

Plot the audit separately with a Python environment containing Matplotlib:

```sh
"$PLOT_PYTHON" Validation/experiments/biotin_single_particle_v1/analyse.py \
  --plot-audit "$ANALYSIS_OUTPUT/audit.json" --destination "$ANALYSIS_OUTPUT"
```

For each observation, report eventual failures detected and eventual passers
incorrectly rejected. Also replay consecutive-failure policies, always using
only observations available before each hypothetical rejection. Report remaining
diffusion steps as a compute opportunity, not measured wall-time savings. No
threshold is promoted: one small ligand-specific sample cannot establish safe
early termination. Recycling produces latent features, not complete structures
on which this same exposure check can run without additional inference.

Manifest: `manifest.json`. Project Lab Book 0151; Validation Lab Book 0031.
