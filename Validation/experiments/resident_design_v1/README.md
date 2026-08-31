# Resident iterative-design validation v1

`campaign.py` freezes a manifest before launch, runs each campaign through the
shipped `nanohunter_run.sh`, and writes one atomic receipt per arm. It never
downloads an MSA and never silently replaces a missing engine.

The default `plan` command is safe and does not launch predictors. `run` refuses
to begin if the installed engine inventory, SUMO MSA, Git commit or manifest has
changed. Use `--engines` or `--arms` for staged smoke tests before the complete
matrix.

```bash
# Example bounded plan; selections are frozen into this output's manifest.
python3 Validation/experiments/resident_design_v1/campaign.py plan \
  --output Validation/output/resident_design_v1/boltz_paired \
  --engines boltz2 --arms standard_off,cycle_wave_off
caffeinate -dimsu python3 Validation/experiments/resident_design_v1/campaign.py run \
  --output Validation/output/resident_design_v1/boltz_paired
```

The complete configuration expands to 18 paired campaigns: six design engines
by the current per-trajectory scheduler, cycle-wave directory scheduling, and a
true cross-cycle resident worker. Every trajectory uses one fixed 80-aa binder,
five redesign cycles and the same cached SUMO MSA and seeds. Helix suppression
and experimental IntelliFold padding are intentionally outside this comparison.
Do not launch it casually: full IntelliFold v2 is materially slower than the
other engines.
Raw outputs are resumable and ignored by Git; receipts, audits and compact
figures should only be promoted after the entire selected manifest passes.

`analyze` records end-to-end wall time, predictor-request time, inverse-folding
time, resident startup time, output cardinality and the model-load count. The
figure script creates transparent Arial SVGs for wall time and speedup relative
to the current implementation.

The Protenix Constraint pocket-only memory optimization has a separate native-
MPS numerical check against the checkpoint's original full attention path:

```bash
~/.iproteinstudio/venvs/NanoHunter_protenix_constraint/bin/python \
  Validation/experiments/resident_design_v1/validate_constraint_shortcut.py \
  --output Validation/output/resident_design_v1/constraint_shortcut.json
```
