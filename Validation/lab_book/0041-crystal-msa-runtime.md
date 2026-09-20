---
entry: 0041
title: Crystal and MSA qualification of Apple runtime changes
date: 2026-09-19
author: Codex
status: in-progress
---

User requests experimental-reference comparisons, MSA diagnosis, OpenFold initialization qualification, and app/GitHub/MCP deployment including Torch2.14 for Boltz and IntelliFold. Existing raw outputs remain immutable. Manifest: Validation/experiments/apple_runtime_release_v4/manifest.json. Baseline HEAD b629789d6187af08ec046f1c8547b5ab5ffb83e1; pre-existing unrelated edits preserved.

Expanded before execution: paired MSA predictions for Protenix v2, Constraint, IntelliFold Flash/Full, existing runtime versus2.14, one seed42 prediction each with full200 steps/10 recycles/FP32. Same frozen8060-row SUMO alignment; actual model MSA tensors audited. First-call times are diagnostic, not throughput estimates. External crystal core query21–96, unchanged from prior comparison. No baseline files modified.

## Protocol and evidence

M4 Max, 40 GPU cores, 64 GB, macOS 26.6.1. Original baseline commit
`b629789d6187af08ec046f1c8547b5ab5ffb83e1`. Release changes isolated in
`.worktrees/runtime214-release`; unrelated NISE and BGX edits are excluded.
Scientific jobs use frozen scripts, sealed runtime/source inventories, checkpoint
hashes, Studio preflight/job_start and the shared GPU execution lease.

Original v2 comparisons explicitly disabled MSA in both arms. The new comparisons
freeze the cached yeast Smt3 alignment: 8,060 rows, 7,716 unique aligned sequences,
SHA256 `c5c2ee22f8430f0144c602338fdb250d6ce69e1f851753bf8a8ce5046702f0ff`.
Protenix v2/Constraint and IntelliFold Flash/Full use 200 steps, 10 recycles,
FP32, one sample, seed 42 and four CPU threads. Model-entry MSA tensors are
recorded. Existing upstream caps remain unchanged. One first prediction per arm
is an accuracy diagnostic, not a throughput estimate; app compilation overlapped
part of this diagnostic, so do not attribute its time differences solely to Torch.

## Crystal comparison

The fixture is yeast Smt3, not human SUMO1. RCSB 3QHT chain A contains the exact
96-residue query with construct extensions; 1UBQ chain A contains the exact
76-residue ubiquitin sequence. Reference mapping checks the complete polymer
sequence and each observed CA identity. Fixed cores are ubiquitin 1–72 and Smt3
21–96, excluding the flexible N-terminus independently of predicted confidence.
Reference files are hashed. Three actual parser/alignment/mask tests passed.
These training-era structures provide context, not blind validation; 3QHT is bound.

Saved single-sequence baseline → Torch2.14 core CA RMSD to crystal, Å:

| Engine | Ubiquitin | Smt3 |
|---|---:|---:|
| Protenix v2 | 0.344 → 3.997 | 8.494 → 8.310 |
| Protenix Constraint | 10.917 → 9.087 | 7.715 → 8.493 |
| IntelliFold Flash | 8.646 → 8.510 | 2.226 → 2.248 |
| IntelliFold Full | 0.392 → 0.395 | 2.280 → 2.350 |
| OpenFold | 19.957 → 11.594 | 15.561 → 51.031 |

MSA-backed Protenix v2 improves to 2.150 → 2.205 Å, with no geometry violations;
its original runtime-equivalence gate passes. Constraint improves to 2.188 →
2.299 Å with no geometry violations. Constraint's runtime-pair core RMSD is
0.516 Å, narrowly outside the original 0.5 Å gate; the gate is not relaxed.
Neither Protenix runtime is promoted by this one-protein diagnostic.

## OpenFold initialization assessment

The original high-confidence-core gate was unavailable because the single-sequence
outputs lacked enough high-confidence residues and contained geometry failures.
An independent crystal-defined core plus a real MSA makes the comparison assessable.
The first new job (`job-a7e912b2799c`) was rejected by the output audit: upstream
silently skipped the query because its MSA basename was unrecognized. No outputs
were produced; those apparent timings are invalid and retained as a failed attempt.
The corrected job uses Studio's existing normalized `colabfold_main.a3m` basename.
The worker now rejects zero/multiple CIFs immediately.

Corrected job `job-9da5f4c19497`: baseline Torch2.6, unchanged checkpoint/settings,
candidate-first order, one warmup and one measured request each. Skipped
initializers are only parameters subsequently overwritten by a strict checkpoint
load, with every skipped parameter's dtype/value verified against that checkpoint.
Measured whole prediction call 42.914 → 26.895 s (37.3% less); both crystal core
RMSDs 1.490 Å, zero geometry violations, runtime-pair core RMSD 0.000004 Å.
Confidence scalars match exactly, maximum PDE difference 0.00000572 Å.
This qualifies the initialization prototype on this fixture; production OpenFold
launchers and Torch version are not changed by this release.

## Integration checks

Boltz2 and shared IntelliFold Flash/Full pins and hash locks updated to Torch2.14.
IntelliFold's required SymPy updated to 1.14. Existing checkpoints/scientific
settings are unchanged. Runtime identity includes Torch version. Installer recovery
now requires the requested version before reusing an interrupted committed runtime;
two executable selection tests pass. Old versioned environments remain available.
Detection marks old shared runtimes incomplete with an update instruction.

The fast suite initially passed 40/41 commands. Its one failure was an isolated
installer test fixture missing the new Boltz runtime-version variable; fixed and
all 11 download-recovery tests passed on rerun. Other 40 commands are unchanged,
including six Swift unit tests and all Swift contracts. Explicit `swift build`
and release app build passed. Packaged resource-bundle contract passed. Original
runtime-lock, installer hardening, component, prediction safety, NESSO cache and
Flash padding checks are recorded alongside the suite log.

## Artifacts and limitations

`Validation/output/apple_runtime_release_v4/`: `CRYSTAL_REPORT.md`,
`crystal_comparison.{json,csv}`, `MSA_REPORT.md`, `msa_comparison.json`,
per-job frozen manifests, receipts, output audits, OpenFold qualification, and
build/test logs. Executable analysis and job factories are under the corresponding
`Validation/experiments/` directory. Prior cache/padding evidence is in entries
0170/0040; source default wiring is carried into this release.

Not tested: other Macs/chips, broad MSA-backed design/interface ranking, statistical
hit rates, blind crystal holdouts or multi-hour memory soak. Same-seed MPS random
draws differ across Torch versions; preserving the old runtime matters for exact
reproduction. No smaller models, fewer steps, disabled guidance, MPNN model/Torch upgrade or
Protenix Mini work. Release/deployment final state will be recorded after validation.

Added a separate OpenFold2.6 versus2.14 MSA pair (job-124407fde933), with initialization optimization disabled in both arms. This prevents confusing initialization qualification on2.6 with runtime-upgrade qualification. Flash MSA pair passes the original gates; core crystal RMSD2.298→2.330 Å and no geometry violations.

All four requested MSA pairs completed: Full IntelliFold core crystal RMSD2.313→2.363 Å; zero backbone geometry violations. Original gates pass for Protenix v2, Flash and Full; Constraint fails only its0.5 Å runtime-pair RMSD gate (0.516 Å). First-call seconds: Protenix21.346→14.119, Constraint20.327→10.854, Flash43.175→29.352, Full303.257→274.466. These are diagnostic times only, not speedup claims. Model-entry MSA rows7716 for Protenix/Constraint and7658 for both IntelliFold models, reflecting unchanged engine preprocessing. SVG/PNG comparison generated and visually inspected.

OpenFold runtime MSA pair completed: Torch2.6.0: core RMSD1.490 Å, mean core pLDDT47.8, geometry violations0; Torch2.14.0: core RMSD2.418 Å, mean core pLDDT79.6, geometry violations0. Original gate remains failed (insufficient baseline high-confidence core and confidence change). Keep OpenFold on2.6; this is separate from its accurate2.6 initialization optimization.

Build42 app installed and launched, build41 bundle retained under build/rollback-build41-20260920. Staged managed setup, locks, MCP server and all optimization helpers byte-match the release worktree. Pre-upgrade detection correctly marks Boltz/IntelliFold runtimes incomplete. Managed engine installation submitted as job-b96d6ec1ecb6 through the admin bridge.

Managed installer completed successfully. Exact metadata confirms Torch2.14.0, NumPy1.26.4 and SymPy1.14.0 in both new versioned Boltz/IntelliFold environments. The ordinary installer also revalidated its unchanged base MPNN dependency environment; no MPNN version or model setting was intentionally changed. Installed public-MCP smoke jobs: Boltz job-2d05362a8239, Flash job-c6bfd238f039, Full job-a1aa0b3f507d. All use the cached MSA, offline-only preparation and one seed/sample.

## Installed app/MCP qualification

All three installed public-MCP prediction jobs completed and passed exact sequence,
MSA SHA256, finite coordinates, one-model cardinality, confidence-matrix and backbone
geometry audits. Boltz potentials enabled, offline-only preparation, full settings.
- boltz 2: crystal core RMSD 2.111 Å; 0 backbone violations.
- intellifold v2-flash: crystal core RMSD 2.330 Å; 0 backbone violations.
  Installed versus isolated Torch2.14 core RMSD 0.00071831 Å; PAE MAE 0.001218 Å. These tiny differences include CLI/resident and production-thread differences; this is not a timing pair.
- intellifold v2: crystal core RMSD 2.366 Å; 0 backbone violations.
  Installed versus isolated Torch2.14 core RMSD 0.01100749 Å; PAE MAE 0.004175 Å. These tiny differences include CLI/resident and production-thread differences; this is not a timing pair.

Installed MCP system_detect reports every engine state=ok, including NESSO, Boltz,
Flash and Full. Completed runs were reviewed through results_overview, followed
by results_query. NESSO installed Engine defaults explicitly enable both caches;
its helpers byte-match the previously validated source. No new complete NISE
design campaign was run during deployment.

Build42 distribution archive built from clean commit
`c455aea960eae3c7ac4d33c5495f503de7ca97b7`; code-signature/resource checks passed.
The existing trusted-beta channel and Sparkle EdDSA signing key are retained.
Source checkout synchronization verified103 unrelated/local-index files unchanged.
