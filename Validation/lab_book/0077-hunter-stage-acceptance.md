# 0077 — Protein Hunter stage handoff acceptance

2026-10-01, in progress. M4 Max / 40 GPU cores / 64 GB. Predeclared protocol:
`experiments/hunter_stages_v1/manifest.json`. Exact adapter/runtime/weight identities
are pinned by each normal iterative plan; raw outputs remain immutable under
`output/hunter_stages_v1`. Uses Studio's existing shared execution lock.

Test RFdiffusion3 → ESMFold2 Fast and Boltz → ESMFold2 Fast/Full, each through two
MPNN/refolding cycles. This is functional acceptance, not an efficacy or speed
comparison. Active benchmark job-bcaf0cacfdda and queued job-643a7569c927 paused
with user approval. A subsequently requested ESM benchmark takes priority; its
watcher owns Protenix/binder resumption (see project lab entry0252 queue handoff).

Core arms passed: RFdiffusion3/Fast gives 2 starts + 4 complete refined structures;
Boltz/Fast and Boltz/Full each give 1 + 2. Per-input coordinates, chain cardinality,
complete MPNN sequences, finite confidence and engine identity pass the output
audit. Uninterrupted refinement uses one model load over two later requests.

Additional Full interruption/resume passed: original start and cycle-01 structure
hashes are unchanged. Original RFD3 attempt failed on absent per-prediction timing
files for generated starts; fixed by recording missing RFD3 timing as absent,
then reran a fresh plan. A ligand test was added (fluorescein, one backbone,
LigandMPNN/Boltz, no affinity). Its first queued plan was canceled before inference
after CPU preflight found an import-path error; corrected retry is queued.

Evidence: output/hunter_stages_v1/audit.json, resume-verification.json, per-arm
immutable plans, runtime bindings and input SHA manifests. No new default
scientific settings, efficacy claim or performance claim are promoted. Not all
engine pairs, ligand chemistries, target sizes or long campaigns were tested.
