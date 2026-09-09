# 0014 — Paired 90-residue monomer control screen

Date: 2026-09-05. Status: complete; final results in entry 0017. The following records the declaration and launch history.

Hypothesis: existing sequence priors, masking and MPNN controls have distinct
effects on secondary structure in unconditioned monomers. Bounded β-specific
initialization inspection may change progression and downstream fold composition.
The experiment does not assume improved folding or β enrichment.

The declared [configuration](../experiments/monomer_secondary_structure_v1/config.json)
has 22 conditions, ten paired trajectories each and five optimization cycles,
all using Boltz-2 and SolubleMPNN at length 90. Baseline, antihelix, β-oriented,
mixed and β inspection are the core contrasts. Additional controls and exact
commands are in the [experiment README](../experiments/monomer_secondary_structure_v1/README.md).
No binding target or ligand is supplied. Empty MSA, cached-MSA checksum: n/a.

Base commit: `37cc95497283025191e7d2067cb35d1af9168d72`, dirty workspace. The
generated manifest records the diff hash and every experiment script; staging
records exact source/runtime hashes, engine code, Boltz-2/SolubleMPNN checkpoint
checksums, package locks, hardware and macOS. Hardware verification occurs before
execution. The receipt verifies Apple M4 Max, 64 GiB memory, macOS 26.6.1,
PyTorch 2.13.0 and MPS available. No completed-campaign results yet.

Each arm's first trajectory counts in its ten and is audited before the
remaining nine. Technical failures stop execution. Initialization budget
exhaustion is recorded explicitly and is not a pass or replaced seed. P-SEA
endpoints exclude cycle 00 and average cycles 01–05 within each trajectory;
conditional structural means report completion n, with attrition retained.
Only the documented SVD fallback is allowed and its log lines are counted.

Prelaunch validation: six campaign contract tests, 14 refinement lifecycle
tests, seven sampler tests, six actual shell integration tests with synthetic
prediction/MPNN adapters and Biotite, and the MCP monomer benchmark contract
passed. The complete 18-test MCP bridge suite also passed (isolated local
loopback test server required sandbox escalation). These are software tests,
not evidence of control efficacy.

At 21:12 UTC the immutable baseline pilot job `job-e1f1a39cd186` started.
Calibration and early cycle predictions show MPS use and the documented
`aten::linalg_svd` warning. Scientific inference is in progress. The usual
calibration calls are extra operational calls, excluded from trajectory n.
A sandboxed CLI status probe could not create its reconciliation state file;
the authorized controller's job-status receipts remain authoritative and the
probe did not alter the job. No automatic approval rejection occurred.

Baseline completed at 21:14:43 UTC. Its one trajectory produced all five
optimized structures and passed the audit. Measured trajectory wall time was
111.383646 seconds, including initialization and excluding separate calibration,
on the M4 Max above. This single smoke is not evidence for a control comparison.
The β-inspection smoke is `job-1a0fad7a2069`; it also counts in the final ten.

The β-inspection smoke completed at 21:17:51 UTC and passed its full audit:
original candidate flagged, second candidate accepted, then all five normal
optimization cycles completed. The original sequence, prediction and decision
remain preserved. All 22 pilot plans passed public preflight. The declared
one-attempt variant is `job-8bf07677f09a`, checking exhaustion without replacement.

The one-attempt pilot ended at 21:19:12 UTC with explicit exhaustion, failed
eligibility and no normal cycles. Its output integrity audit passed; its
scientific outcome remains a failure to progress. At 21:19:47 UTC the full
controller launched detached with `caffeinate -dimsu` (PID 89270), reusing all
three smoke jobs and continuing the remaining declared conditions. See
`Validation/output/monomer_secondary_structure_v1/controller_launch.json`,
`controller.log`, and per-arm `status/` receipts. Final comparison is pending.

Untested: full real-model comparison is still running; other lengths/models/MSAs,
full strength sweeps and interactions, binding, experimental folding, memory
soak and default promotion. See project [0096](../../lab_book/0096-monomer-secondary-structure-benchmark.md).
