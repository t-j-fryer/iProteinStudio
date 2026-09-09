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
python3 Validation/experiments/binder_helix_strength_all_engines_v7/campaign.py \
  validate-target --target-name my_target --target-sequence-file /path/target.fasta \
  --target-msa /path/target.a3m
python3 Validation/experiments/binder_helix_strength_all_engines_v7/campaign.py stage
python3 Validation/experiments/binder_helix_strength_all_engines_v7/campaign.py \
  prepare --target-name my_target --target-sequence-file /path/target.fasta \
  --target-msa /path/target.a3m
python3 Validation/experiments/binder_helix_strength_all_engines_v7/campaign.py plan --pilot-only
python3 Validation/experiments/binder_helix_strength_all_engines_v7/campaign.py run --pilot-only
python3 Validation/experiments/binder_helix_strength_all_engines_v7/campaign.py run
```

`run --pilot-only` executes and audits one trajectory in every arm. The full run
will not expand an arm unless its pilot passed. Plans and jobs use Studio's
immutable MCP bridge, shared Apple-GPU lock, required target-MSA policy, and
measured scheduler. No target structure or epitope is assumed.

V1 stopped at its first preflight plan, before any inference, because the frozen
template was outside the broker's import roots. V2 corrected the managed input
boundary but stopped after its first completed Boltz pilot: the independent
auditor incorrectly searched the per-run folder for resident cycle-wave native
files. V3 corrected that check, but its completion predicate still required the
run scheduler's per-run exit receipt; resident jobs instead emit a zero-valued
batch receipt for every cycle. V4 validates either receipt layout, always
requiring complete cycle cardinality and a completed broker state. It otherwise
preserves the same design and does not reuse earlier inference output. V4 then
stopped after IntelliFold inference because `complex_plddt` is a Boltz-only
confidence field. V5 records `complex_plddt` and ipSAE(min) when available and
leaves them null otherwise; iPTM remains required for every trajectory. V5 then
stopped fail-closed after twelve successful pilots because the MCP planner
assigned OpenFold3 to the unsupported resident scheduler. V6 keeps the same
design but uses OpenFold3's established `run` scheduler and does not reuse
earlier inference output. V6 then showed that OpenFold's raw-MSA parser silently
filters arbitrary A3M basenames and that the controller's per-arm pilot gate did
not implement the declared global gate. V7 gives every OpenFold chain a private,
byte-identical `colabfold_main` MSA path and requires all fourteen pilot audits
to pass before any trajectories 2–10 can start; it does not reuse v6 inference.
