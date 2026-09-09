# Mixed secondary-structure pilot

Tests the existing mixed implementation with beta/composition/pattern/turn
strengths 0.50 and anti-helix strengths 0.25 or 0.50. Each has a seed-only and a
sustained arm with identical cycle-00 sequence. One trajectory per arm, 90 residues,
aCbx, Boltz/SolubleMPNN, five optimized cycles and the prior fixed seeds/MSA.
This is four trajectories, 24 predictions including four initial structures.

The runner/helper hashes must match the completed five-arm controls. Only the
priors change. The native app and installed scripts are not restaged. Independent
post-predictions remain disabled as in the original mechanistic experiment.

Call the bridge workflow guide and system detection before planning. Then:

```bash
python3 Validation/experiments/secondary_structure_mixed_v1/campaign.py prepare
# Review manifest_smoke.json and all four normalized plans before starting.
python3 Validation/experiments/secondary_structure_mixed_v1/campaign.py start
python3 Validation/experiments/secondary_structure_mixed_v1/campaign.py status
```

Outputs live under `Validation/output/secondary_structure_mixed_v1` and link into
a dedicated managed validation project. Submission uses the shipped client-neutral
bridge, immutable plan digests and shared execution lock. Never edit completed raw
outputs. These single-trajectory arms can test wiring and illustrate outcomes;
they cannot establish efficacy, select an optimum or justify a default.
