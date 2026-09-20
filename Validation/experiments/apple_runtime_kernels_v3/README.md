# Apple runtime kernels v3

Fixed-input same-runtime experiments on M4 Max, recorded in project0170 and
Validation0040. See manifest.json and each frozen/run.json for declared settings.

Run `preflight.py ENGINE STAGE --start` with the existing system Python. It creates
a content-addressed Studio plan, fingerprints scripts/assets, and uses job_start
under the shared exclusive GPU lease. Engines: boltz, protenix, nesso. Stages are
a closed list in preflight.py; this is not an arbitrary command endpoint.

Existing isolated environments/seals from runtime v1/v2 are read-only dependencies.
No environments or checkpoints are modified. Raw output blocks are immutable and
receive a complete inventory receipt. The coordinator resumes only verified blocks
and retains unfinished attempts. `status.py` reads the real broker; `recovery.py`
performs the one recorded NESSO cache cancellation/resume test.

`report.py` independently audits structures/scalars and reconstructs figures.
`preprocessing_audit.py` compares the saved NESSO parser arrays, allowing RNG/input
changes to be distinguished from arithmetic changes. All structural SUMO gates
use analysis_policy.json; unknown core remains unassessable.

The final REPORT.md/DECISIONS.md under Validation/output/apple_runtime_kernels_v3
distinguish operator wins, complete-request wins, diagnostic variants and deployed
source changes. A faster operator is not a complete-model speed claim.
