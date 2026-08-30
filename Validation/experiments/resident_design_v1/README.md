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

The complete configuration expands to 20 campaigns. Do not launch it casually:
full IntelliFold v2 alone is materially slower than the other bounded smokes.
Raw outputs are resumable and ignored by Git; receipts, audits and compact
figures should only be promoted after the entire selected manifest passes.

Secondary structure is assigned from predicted coordinates with Biotite's P-SEA
implementation. The analyzer reuses the managed Protenix environment when
available and never substitutes sequence propensity for measured structure.

The Protenix Constraint pocket-only memory optimization has a separate native-
MPS numerical check against the checkpoint's original full attention path:

```bash
~/.iproteinstudio/venvs/NanoHunter_protenix_constraint/bin/python \
  Validation/experiments/resident_design_v1/validate_constraint_shortcut.py \
  --output Validation/output/resident_design_v1/constraint_shortcut.json
```
