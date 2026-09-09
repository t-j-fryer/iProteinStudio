# Initialization helix strength across installed engines

User-authorized 90-aa unconditioned monomers, 10 trajectories × 5 optimized cycles per arm. Three strengths (0, 0.5, 1), seven installed predictor variants. SolubleMPNN, empty MSA, seed-only control, 50% default mask (OpenFold native substitution retained), MPNN temperatures 0.3 then 0.1. Native prediction defaults fixed within engine; no model substitution.

`campaign.py stage`, `prepare`, then `run` use public immutable MCP plans/jobs, shared execution lock, snapshot and provenance checks. Pilot trajectory belongs to the ten; remaining nine require an audited smoke. Completed raw output stays immutable. Analysis uses coordinate P-SEA and finite CA confidence, validates sequence and cardinality and excludes cycle00. Failures are retained; no replacement seeds.

Continuation after the no-template IntelliFold launch failed before inference. The three audited Boltz pilot trajectories are reused by raw/audit checksum and count in the same n=10. No seed, model setting or weight changes. V1 raw outputs and failed job remain immutable.
