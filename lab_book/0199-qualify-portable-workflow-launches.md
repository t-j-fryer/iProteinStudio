---
entry: 0199
title: Qualify real engine launches before release and resume biotin
date: 2026-09-26
author: Codex
type: experiment
status: in-progress
machine: Apple M4 Max, 64 GiB unified memory, macOS 26.6.1
---

## Context

User requested safely stopping the current biotin campaign, testing every
compatible engine through Protein Hunter, RFdiffusion3, NISE and Predict,
fixing failures, publishing/updating the app and MCP, then resuming biotin.
This follows portable activation defect 0198. No model-performance claim.

## Protocol

Harness/configuration: `Validation/experiments/portable_workflow_launch_v1/`.
Raw outputs/receipts: `Validation/output/portable_workflow_launch_v1/`.
Use managed plans, immutable digests and the shared execution lease for GPU work.
Small output budgets, unchanged engine diffusion/recycle/precision defaults.
Review result overviews and audit structure cardinality, sequences, finite
coordinates and confidence files. Preserve failed attempts. No student-target
rerun or high-budget new campaign. Never mutate retained biotin code/settings.

## Status

Biotin job `job-221c7d6db092` stopped through the broker; state cancelled,
no error, execution lease free. 10,403 existing completion receipts hashed
before stopping. Same plan/digest must be resumed after installed acceptance.
Engine detection reports all supported components installed.

## Limits

The declared launch matrix passed with the scientific-stop qualifications below.
Fresh-Mac/cross-chip performance and long-run science acceptance are separate.

## Additional integration defect found

The first real small-molecule RFdiffusion3 case completed backbone generation,
LigandMPNN, and primary Boltz inference, then failed with `Unsupported predictor(s):
boltz`. Its public MCP request had included Boltz in `extra_predictors`, which the
schema and preparer accepted, but the ligand second-opinion adapter rejects.
Native Studio already removes this redundant primary engine. Match that behavior
in MCP normalization and direct/saved request preparation; retain independent
extras and the mandatory primary Boltz/affinity work. Preserve the failed case
`rfd3-ligand`; queue a fresh `rfd3-ligand-retry` through source MCP29 with the same
scientific request. No component package or frozen failed plan was modified.

Regression: MCP bridge 19 tests and workflow pipeline contracts pass. The latter
also exposed a stale test hardcoding the former IntelliFold PyTorch2.6 pin; it now
checks the launcher against the installed-version lockfile (currently2.14).
All 58 fast-suite commands passed, including ten sandbox-blocked checks rerun with
normal process/local-network/compiler access. `swift build` passed in the main
and isolated release worktrees. No throughput claim.

## Further integration findings

- OpenFold's explicit-empty binder plus cached target MSA request failed inside
  upstream `create_main`: its auto-generated NPZ is keyed `dummy`, absent from
  the configured source order. The shared query adapter now materializes the
  requested single query as `colabfold_main.a3m` only in mixed-MSA requests.
  Target alignment bytes remain unchanged; all-empty inference still disables
  MSAs; no server fallback is introduced. Workflow executable regression passes.
- The broker previously treated every surviving child immediately after parent
  exit as an orphan. It now retains the execution lease for two seconds of
  orderly shutdown, then preserves owned-process evidence and performs the
  existing termination/escalation. Actual prediction errors survive cleanup.
  All 22 broker tests pass, including real detached child shutdown, orphan
  termination, cancellation/queueing, and failure-message preservation.
- RFdiffusion3 feature names intentionally anonymize atomized ligand atoms to
  element symbols. The MLX PDB writer incorrectly reused these as identifiers,
  yielding repeated C/O names and failing NISE's strict ligand handoff audit.
  Feature capture now stores original atom names and elements as separate export
  metadata. The writer validates cardinality, uniqueness and element order, and
  changes only exported names/elements. Model feature arrays and coordinates are
  not edited. Old ambiguous ligand fixtures fail with a regeneration instruction.
  Three writer regressions and 18 RFdiffusion3 audit regressions pass.

Derived a new portable RFD3 package from the installed verified closure, changing
only `milestone0_oracle.py` and `scripts/generate_backbones.py`; 36,894 inventoried
files are unchanged. New identity:
`c9fc19327d6b15b5a14b83b3d99c914e1dc52d2b2d1eb9e87b6cf0be49d27a3a`.
Archive 396,215,713 bytes, SHA256
`a626ce5ab19bca66b25f128935db64387a9621602654f17517c8d92d900a9ea8`.
No weights included. Inventory verification and relocation imports pass; the
sandboxed import emitted a Metal-at-exit diagnostic, so GPU qualification relies
on the subsequent normal-session managed activation and real jobs, not that import.
Transactional activation retains the old runtime and every existing binding.

Queued acceptance attempts were cancelled before execution to permit safe
staging under registry/execution/install locks. Fresh `*-fixed` plans preserve
those attempts and use the new code/runtime; no frozen plan was patched.
The single-start Boltz NISE attempt reached the Phase0 cycle02 structural gate
and had no survivor. Retain this as a scientific rejection, not a launcher defect.
A three-start diagnostic attempt exercises downstream work without weakening
geometry gates. No proposed scientific default or speed claim.

The broader science-fixture suite passed 17/19 initially. Two test-environment
issues were isolated: objective test lacked its own NANOHUNTER_ROOT setup, and
RFD3/NISE ligand tests require Boltz imports absent from the Protenix test Python.
The objective test now declares its source root; both files pass (three tests
each) under the installed Boltz/RDKit Python. No model inference in these tests.

## Installer process classification

Code review of the final managed update path exposed the old `pgrep` expression
matching all `components/` processes, including the MCP installer worker's own
control Python. Replace the broad expression with literal managed-path checks
from one process snapshot: ignore the control interpreter, retain guards for
engine components (including future names), legacy venvs, and live runtime views.
Two executable regressions use owned inert child processes and a managed path
with spaces and regex characters: control is allowed; all four computation
path classes are blocked. No unrelated processes are signalled or changed.

The real paired RFdiffusion3 retry confirms all 44 prior input arrays are exactly
identical; only the two export metadata arrays were added. All 276 saved atom
coordinates are identical (maximum difference 0.0 Å), protein PDB lines are
identical, and the 16 unique ligand names now exactly match the prepared molecule.
The NISE handoff has passed and advanced into sequence scoring. Independent
GitHub download/archive extraction verifies all 36,896 inventoried runtime files
and confirms the published candidate contains no model weights.

The three-start Boltz NISE case completed three Phase0 cycle01 affinity
evaluations. The gate-stage Cα RMSDs were 8.367, 10.766 and 2.973 Å, all exceeding
the unchanged 2.0 Å cutoff, so it correctly stopped without optimization seeds.
Audit this as a scientific diagnostic stop, with the partial trajectory and raw
candidates retained; do not claim a completed optimization cycle.

## Output-quality boundary

OpenFold completed both Hunter cycles and the fixed broker recorded completion.
The random binder fixture nevertheless carries 128 recorded continuity warnings
per cycle, also present in its unmodified raw prediction, with low complex
confidence. These launch checks do not qualify such designs for experiments.
The natural SUMO monomer prediction has finite matching coordinates and zero
Cα steps outside 2.8–4.5 Å (observed range 3.7171–3.8004 Å). No model settings or
geometry gates were relaxed to hide the binder warnings.

The PSICHIC NISE attempt saved finite affinity and binding-proxy scores, then
its single candidate failed the unchanged Phase0 structural gate. This covers
launch/scoring and an actionable scientific stop, not a full PSICHIC optimization
cycle. NESSO NISE completed optimization cycle1 after the RFdiffusion3 export fix.
The CPU output auditor excludes prepared ligand PDB/CCD assets from the predicted
protein-structure set; these input chemistry files correctly contain no protein
Cα atoms. No unexpected CPU-fallback lines were found in completed runs.

## Portable Protenix Constraint receipt defect

The real constrained-Protenix launch failed before loading its model: its portable
installer wrote the patch/source hashes but omitted `zero_substructure`, required
by the prediction adapter. The installed source carries the validated patch;
this is a receipt contract defect, not evidence that an unpatched model is safe.
The portable installer now writes the same contract marker as the source installer.
Detection checks it too, so affected installations show Update rather than Ready.
A real-file portable receipt regression exercises the installer and Bash detector:
fresh receipt accepted, old incomplete receipt rejected. Four portable-installer
regressions pass. Repair and prediction retry use new public plans; the failed
frozen attempt remains intact.

The first normal installer attempt correctly refused while the CPU output auditor
was still running under an engine interpreter. That process then exited; the
same installation plan was resumed through MCP with the guard intact. This is
preserved as `engine-install-busy-guard.json`, not counted as an installer defect.
The retry exercises public GitHub runtime delivery and standard dependency
installation, with all previous immutable runtime directories retained.

## Final launch acceptance

All 23 current cases passed their output audits: 21 completed and two NISE cases
ended in the explicitly documented zero-survivor scientific gate. All 39 attempts,
including superseded failures and cancelled-before-execution jobs, remain saved.

| Workflow | Coverage | Outcome |
|---|---|---|
| Predict | Boltz, IntelliFold Flash/full, Protenix v2/Mini, OpenFold | 6 completed |
| Protein Hunter | Seven predictors including Protenix Constraint; AntiFold, AbMPNN, target-template nanobody and LigandMPNN cases | 11 completed |
| RFdiffusion3 | Two protein cases covering all supported verifiers; ligand backbone/MPNN/Boltz holo+apo | 3 completed |
| NISE | Boltz, NESSO and experimental PSICHIC scoring; LASErMPNN | NESSO cycle1 completed; Boltz/PSICHIC scoring completed before structural rejection |

The normal MCP installer `job-dc7a24879773` completed with `NHDONE|ok`. It exercised
the control, MPNN and Boltz dependencies plus RFdiffusion3 and Protenix Constraint;
existing model files were reused after verification. The repaired constrained
Protenix run `job-ebaeff102eff` completed calibration and both Hunter cycles.
The unchanged scientific runtime identity is
`0385c1eafa5c23e62d69b535101db17358e97cc95566df6e31d234940c688617`.

Compact public evidence, plan/snapshot identities and runtime fingerprints:
[launch-evidence.json](artifacts/0199-workflow-launches/launch-evidence.json).
Full local audit: `Validation/output/portable_workflow_launch_v1/REPORT.md` and
`output-audit.json`. Public `results_overview` receipts cover the grouped runs.
No unexpected CPU-fallback lines appeared. Physical-quality warnings described
above remain visible; a passed file audit is not a claim of experimental quality.

Runtime published and anonymously downloadable:
[runtimes-2026.09.26-1](https://github.com/t-j-fryer/iProteinStudio/releases/tag/runtimes-2026.09.26-1).
The app publication, installed-bundle verification and exact production resume
are the remaining deployment steps; append their observed receipts below.
