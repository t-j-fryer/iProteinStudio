# Secondary-structure sequence-prior validation

Five paired aCbx/Boltz/SolubleMPNN arms test whether anti-helix and β-oriented
priors matter only through cycle 00 or must remain active during redesign. Each
full arm contains 10 fixed-length 90-aa trajectories and five optimized cycles.
The same trajectory, MPNN and predictor seeds are used in every arm. Mixed mode,
loop kill and independent post-predictions are deliberately excluded.

```bash
python3 Validation/experiments/secondary_structure_priors_v1/campaign.py prepare --phase smoke
python3 Validation/experiments/secondary_structure_priors_v1/campaign.py start --phase smoke
python3 Validation/experiments/secondary_structure_priors_v1/campaign.py status --phase smoke
python3 Validation/experiments/secondary_structure_priors_v1/campaign.py gate-smoke
python3 Validation/experiments/secondary_structure_priors_v1/campaign.py prepare --phase full
python3 Validation/experiments/secondary_structure_priors_v1/campaign.py start --phase full
```

Jobs use Studio's MCP v8 immutable plans, shared execution lock, pipeline
snapshot and resident Boltz scheduler. Generated data live under
`Validation/output/secondary_structure_priors_v1/`.

After completion:

```bash
python3 Validation/experiments/secondary_structure_priors_v1/analyze.py \
  --campaign-root Validation/output/secondary_structure_priors_v1/campaigns \
  --output Validation/output/secondary_structure_priors_v1/analysis/psea_per_structure.csv
```

Cycle 00 is retained as the manipulation check but excluded from design
endpoints. β enrichment is accepted only if P-SEA sheet assignment rises rather
than merely converting helix to coil, without gross loss of confidence,
interface quality, geometry or sequence diversity.

Completed results and the audit are recorded in [Validation Lab Book 0007](../../lab_book/0007-secondary-structure-comparison-results.md). After P-SEA, run `summarize.py --root Validation/output/secondary_structure_priors_v1` with a prepared Biotite/NumPy interpreter to reproduce the paired summaries.
