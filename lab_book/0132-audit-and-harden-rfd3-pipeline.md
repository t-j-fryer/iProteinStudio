---
entry: 0132
title: Audit and harden the active RFdiffusion3 pipeline
date: 2026-09-16
author: GPT-6 Codex
type: bugfix
status: complete
machine: Apple M4 Max, 64 GB unified memory; CPU/software tests, no new GPU campaign
tags: [rfd3, nise, resume, validation, audit]
---

## Context

After [[0131-audit-test2-nise-runs]] identified the empty buried-atom metrics crash,
the user requested an audit and fixes across RFdiffusion3. Scope was the active
Studio/MCP paths: ligand and protein input preparation, de novo/partial/motif
generation, the NISE backbone adapter, sequence design, prediction, ranking and
resume. Unused upstream experiment/plotting scripts and neural model internals
were not treated as validated product paths.

## What was done

Read the active runners and existing tests, ran installed-component detection,
replayed saved failed-run fixture arrays through the repaired metrics code, and
added executable regression cases. The main changes are in the bundled
`rfd3_overlay/scripts/`, with matching preflight checks in `rfd3/prepare_campaign.py`,
the protein campaign orchestrator, the Swift request model and MCP plans/schema.

| Verified problem | Repair | Evidence |
|---|---|---|
| Empty optional buried/exposed or fixed-interface subsets crashed reductions | Record unavailable distances as null; zero contacts; handle one-residue segment diagnostics | Four selection combinations, monomer/single-residue tests; five actual saved NISE fixtures |
| Non-finite coordinates or incomplete exported backbone could reach downstream work | Fail invalid coordinates and report missing backbone atoms | Numeric/export regression cases |
| Fixture reuse trusted a filename, even after conditioning/input changes or partial creation | Bind fixture spec, source/CCD hashes and generation parameters; validate NPZ arrays; verify artifact receipts; preserve interrupted output | Changed selection/input, missing fixture and repeat-without-rebuild tests |
| Standard generation bypassed the audited NISE batch path | All generator calls use batch receipts and seed cursor; reject unaudited legacy results and overwriting | Existing interruption/tamper tests and NISE generator replay |
| Three/four queues reused seed ranges belonging to the next bin | Reserve disjoint per-queue/per-bin attempt ranges; preserve usual two-queue layout | Range-disjointness tests for 1–4 queues |
| Cached bins skipped verification; queue failures hid the useful traceback and could leave peer work running | Re-enter audited queues, verify exact quota, reject stale flat outputs, surface worker error and terminate peers | Real subprocess failure/peer-termination fixture |
| Campaign progress labels skipped damaged or changed completed stages | Bind campaign configuration; re-enter stages to verify their unit-level caches; atomic progress writes | Route/resume tests and corrupted artifact tests |
| MPNN restart regenerated completed backbones; LASErMPNN reused unverified FASTAs | Content-bound per-backbone receipts, sequence count/length/alphabet checks, archive uncommitted files; monitor MPNN completion while its model stays loaded | Terminate whole fake MPNN process group after first receipt; retry only unfinished backbone; tamper rejection |
| Ligand runner silently mapped `proteinmpnn`/unknown choices to SolubleMPNN | Exact explicit model mapping, reject unsupported names, pass the declared runtime root to both designers | Routing regression (GUI/MCP still restrict ligand choices to their existing allowed models) |
| Predictor input directories could retain stale YAMLs or silently overwrite duplicate names | Validate names/cohort, bind sequence/template requests, verify generated YAMLs; require chain A to be the actual first entry | Input-set tests and existing workflow tests |
| Prediction reuse relied on structure/confidence filenames or chunk names | Hash exact inputs/alignments/model choice and completed outputs; archive uncommitted output; fail successful exits with missing output; preserve resident/wave scheduling | Resident and wave replay without an extra model load; corruption/changed-input and affinity-chunk tests |
| NaN/Inf/out-of-range scores entered ranking; extra unrequested engines affected protein mean | Reject invalid score components, rank only requested engines, reject ambiguous duplicate engine rows | Ranking regression cases |
| One missing checking engine could be hidden by another engine's good geometry | Require a finite value from every requested checker for an enabled aggregate gate | Missing/None/NaN aggregate tests |
| `.bcif` was sent to the text-CIF reader; insertion-coded residues were undercounted | Use BinaryCIFFile and include insertion code in residue identity | Actual binary-CIF round trip and preflight |
| UI/MCP accepted one diffusion step although the generator rejects it; contradictory exposure controls passed preflight | Match the minimum of two steps, retain zero recycles, reject simultaneous buried/exposed conditions | Swift request harness and MCP plan tests |
| Preflight provenance did not cover all nested RFdiffusion3 helpers and MLX sampler sources | Share runtime source discovery between native and MCP plans | Changing a sampler or resume helper after preflight invalidates the plan |

Updated the overlay deployment stamp/checksum, CLI documentation, and test-runner
registration. The earlier audit artifacts and all scientific campaign outputs were
preserved. No active worker, installed application or frozen campaign runtime was
replaced during this task.

## Results

- **13 targeted Python test files passed**; [machine-readable results](artifacts/0132-rfd3-pipeline-audit/tests.json)
  link their logs. This includes **18 new audit regression cases**, plus existing
  motif/partial, atom conditioning, surface-origin, target export, EMA provenance,
  prediction scheduling, NESSO and NISE/RFD3 adapter coverage.
- **17 MCP bridge tests passed**, including the new preflight assertions. The
  loopback gateway test required running outside the network-restricted sandbox;
  its initial sandbox failure was a bind-permission error, not a code failure.
- **17 desktop job tests passed**, including nested RFdiffusion3 helper provenance
  and existing shared-queue ownership contracts. Both MCP and desktop suites were
  rerun after the final provenance change; no scientific models were launched.
- The focused Swift workflow-request harness passed. Its old protein fixture
  needed to declare the current surface-scan policy rather than inherit the
  small-molecule COM default; it is now registered in the standard Swift harness.
- `swift build --disable-sandbox --skip-update` passed with module caches under
  `/private/tmp`. The initial plain build failed because its default cache was
  unwritable; setting writable cache paths resolved the failure.
- All five saved RFD3 fixtures from the failed NISE run now produce strictly
  JSON-serializable metric dictionaries with null buried distance. The replay uses
  saved feature arrays/initial coordinates, **not newly predicted structures**:
  [fixture checksums and results](artifacts/0132-rfd3-pipeline-audit/failed-fixture-replay.json).

No new throughput measurements or scientific efficacy claims. Timing printed by
fake-model test harnesses is not a benchmark.

## Decision and rationale

Kept scientific defaults and model scheduling. Empty optional selections are valid
requests; inventing buried atoms would alter the user's experiment. Missing checks
and invalid scores must fail qualification rather than improve a rank. A saved
progress label or filename is weaker evidence than verified inputs and outputs.

Old unreceipted fixture/backbone results are not retroactively certified. Use a new
campaign directory for the repaired runtime; old managed jobs retain their frozen
code and provenance. A changed request never silently reuses old scientific work.
Do not weaken the NISE gate in response to the separate NESSO/PH no-survivor outcome.

## Reproduce

From the canonical Studio checkout:

```bash
bash "$HOME/.iproteinstudio/setup_pipeline.sh" --detect
MPLCONFIGDIR=/tmp/iproteinstudio-audit-matplotlib \
  "$HOME/.iproteinstudio/rfd3/.venv/bin/python" Tests/test_rfd3_audit_regressions.py
"$HOME/.iproteinstudio/rfd3/.venv/bin/python" Tests/test_workflow_pipelines.py
"$HOME/.iproteinstudio/rfd3/.venv/bin/python" Tests/test_ligand_screening.py
"$HOME/.iproteinstudio/venvs/NanoHunter_boltz/bin/python" Tests/test_nise_rfd3.py
python3 Tests/test_rfd3_predictor_scheduling.py
python3 Tests/test_mcp_bridge.py
python3 Tests/test_desktop_jobs.py
CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-modules \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-modules \
  swift build --disable-sandbox --skip-update
```

The complete targeted Python file list is in `tests.json`. The science test group
also registers the new cases; it needs a prepared Python environment with the
Boltz/RDKit/Biotite dependencies, not just system Python.

## Limits and what was not tested

This is a broad audit of active orchestration paths, not proof that every possible
error has been eliminated. No new real-model generation→MPNN→folding campaign,
GPU throughput/memory benchmark, experimental binding validation, live GUI click
test, DMG/release build, installed-app update or GitHub publication was performed.
Neural inference was replaced at test boundaries. Existing model/weight checks
passed detection and provenance tests; upstream checkpoint mathematics were not
reaudited. Legacy research scripts outside active Studio launch paths remain
outside the supported coverage. Normal process-group interruption is tested;
power-loss/fsync durability is not.

## Next

Before a repaired large campaign, run a new managed 1–5-backbone end-to-end smoke
test with the exact nine-hotspot/four-exposed ligand conditioning, using a new plan
and output directory. Package/deploy the changed app when requested. Historical
NISE winner qualification is a separate finding in entry 0131, not changed here.
