# Previous-parent biotin partial-noising test

Requested by the user after the five-start pilot lost every lineage before
optimization. Import its predecessor campaign's qualified top candidate,
`c06_t1_n0_s58`, with its original self-consistency reference and ligand map.
Recompute strict parent geometry and current Bind/Expose checks before inference.

Exercise the actual `partial_noising.run_branch`: two masked predictions using
6 Å heavy-atom neighbourhoods and 25% masking; select the best geometry-passing
Boltz combined score; three LASErMPNN repairs; fold/filter/score those and reserve
one winner. Use the cycle-2 policy (backbone RMSD <2.5 Å, ligand RMSD recorded but
not yet gated), the nine reviewed head hotspots and only terminal O18/O19 exposure
>=50%. Geometry precedes selective affinity. Empty MSA and one resident MPS worker.

This test has at most five structure predictions. Ordinary sampling, beam mixing,
initial generation and convergence are not exercised. It does not establish
improved binding, full-size sampling behaviour or speed. No full campaign starts
automatically from these scripts; the previous failed pilot remains unchanged.

`request.json` retains the campaign contract; initial-generation/ordinary budgets
are unused, explicitly zeroed in the branch-test plan's budget. The private typed
`nise_branch_test` planner copies and fingerprints inputs and scripts. This is a
separate validation job, not a fabricated resume checkpoint.

From the repository, with `NANOHUNTER_ROOT` set to the managed installation:

```bash
python3 Validation/experiments/biotin_parent_noising_v1/prepare.py \
  --source-run nise-C9CCE180-9E41-4BA3-95AE-CB03FBB867FA \
  --records Validation/output/biotin_parent_noising_v1
# Review output/plan.json, then MCP job_start with its id and sha256.
# After job completion, using the managed Boltz Python:
python Validation/experiments/biotin_parent_noising_v1/audit.py \
  --output "$RUN_OUTPUT" --report Validation/output/biotin_parent_noising_v1/audit.json
```

The plan records all source/model fingerprints. Generated outputs stay in the
managed run and ignored Validation output directory. LASErMPNN proposals are saved
and reused on resume; its upstream sampler does not expose seeded sampling.
