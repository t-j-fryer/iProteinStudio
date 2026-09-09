# Sequence-first beta sampling comparison

The complete 90-residue starting sequence is sampled with the existing beta
strand/turn grammar, then an independent mask replaces exactly 45 positions with
X. Paired beta-only and mixed arms share the grammar and mask, with different
amino-acid draws induced by helix-kill weighting. No binder coordinates are used.

| Setting | Beta only | Beta plus helix kill |
|---|---|---|
| Beta residue / pattern strengths | 1.0 / 1.0 | 1.0 / 1.0 |
| Turn strength | 0.5 | 0.5 |
| Effective helix-kill strength | 0 | 0.5 |
| Application | Starting sequence only | Starting sequence only |
| Full trajectories / optimized cycles each | 10 / 5 | 10 / 5 |
| Predictor / designer | Boltz2 / SolubleMPNN | Boltz2 / SolubleMPNN |

The beta arm saves the inactive anti-strength default 0.5 because the existing
beta mode forbids an anti-strength CLI argument and ignores that setting. It
does not apply helix kill. Both arms use normal MPNN after initialization.

The opt-in sampling order preserves the old default and deterministic replay
streams. The local helix-kill rule sees all previously sampled residues before
masking. Each trajectory saves the unmasked sequence, independent mask positions,
masked sequence and full positional plan for exact reconstruction.

## Run and audit

Use the installed runtime. `stage.py` checks the shared execution lock and job
registry before replacing only the reviewed runner and sampler, with backups.
Run the workflow guide and engine detection before scientific planning.

```sh
python3 Validation/experiments/secondary_structure_seed_mask_v1/stage.py
python3 Validation/experiments/secondary_structure_seed_mask_v1/campaign.py prepare --phase smoke
# Review normalized requests, previews and provenance before start.
python3 Validation/experiments/secondary_structure_seed_mask_v1/campaign.py start --phase smoke
python3 Validation/experiments/secondary_structure_seed_mask_v1/campaign.py status --phase smoke
```

After both smoke jobs complete, inspect `results_overview`, then use the managed
scientific Python containing Biotite/NumPy to run:

```sh
python audit.py --root ../../output/secondary_structure_seed_mask_v1 --phase smoke
```

The audit path above is relative to this experiment directory. An operationally
passing smoke audit permits `campaign.py prepare --phase full`, review, then
`start --phase full`. Run the same audit with `--phase full` after completion.
The first full trajectory repeats the smoke seed and is not an extra replicate.

## Endpoints and limits

Primary endpoints are binder P-SEA sheet/helix fractions, averaging cycles 01–05
within each trajectory and then all ten trajectory means. Cycle 00 is an
initialization manipulation check. The primary contrast is paired mixed minus
beta. Confidence, interface scores, diversity and sequence complexity accompany
the structural results. Final-cycle results are labelled separately.

An operational smoke pass does not require beta enrichment. A negative
scientific result is still a completed experiment. The 25% sheet and <40% helix
targets apply to full cohort means without selecting successful structures.
Historical natural and weaker beta controls are descriptive comparisons, since
sampling order/strength changed. No independent post-predictions, experimental
folding/binding measurements or default promotion are part of this comparison.
