# Target-agnostic binding helix-strength benchmark

This is the protein-binding counterpart to `helix_strength_all_engines_v3`.
It compares initialization-only helix-kill strengths 0 and 1 across the same
seven installed predictor variants, with ten paired 90-aa trajectories and five
optimization cycles. Cycle 00 is initialization and is excluded from endpoints.

The target is deliberately not bundled into the experiment. Supply one FASTA
(exactly one protein record) and one A3M or Stockholm alignment. `validate-target`
checks the inputs without creating or launching a campaign. `prepare` copies the
exact bytes under ignored output, records SHA-256 checksums, and refuses any later
sequence/MSA change. The alignment's first query must exactly equal the FASTA
sequence after removing alignment gaps and A3M lowercase insertions.

```bash
python3 Validation/experiments/binder_helix_strength_all_engines_v2/campaign.py \
  validate-target --target-name my_target --target-sequence-file /path/target.fasta \
  --target-msa /path/target.a3m
python3 Validation/experiments/binder_helix_strength_all_engines_v2/campaign.py stage
python3 Validation/experiments/binder_helix_strength_all_engines_v2/campaign.py \
  prepare --target-name my_target --target-sequence-file /path/target.fasta \
  --target-msa /path/target.a3m
python3 Validation/experiments/binder_helix_strength_all_engines_v2/campaign.py plan --pilot-only
python3 Validation/experiments/binder_helix_strength_all_engines_v2/campaign.py run --pilot-only
python3 Validation/experiments/binder_helix_strength_all_engines_v2/campaign.py run
```

`run --pilot-only` executes and audits one trajectory in every arm. The full run
will not expand an arm unless its pilot passed. Plans and jobs use Studio's
immutable MCP bridge, shared Apple-GPU lock, required target-MSA policy, and
measured scheduler. No target structure or epitope is assumed.

V1 stopped at its first preflight plan, before any inference, because the frozen
template was outside the broker's import roots. V2 preserves that receipt and
places the identical target/MSA/template content under a managed runtime input
directory; it does not widen the broker's filesystem policy or reuse output.
