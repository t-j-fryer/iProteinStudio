---
entry: 0291
title: Integrate RCSB discovery and validated MCP workflows
date: 2026-10-02
author: Codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [mcp, skills, orchestration, reproducibility, ui]
---

## Context

The user approved the concrete recommendations from [0289](0289-refresh-figure-one-and-agent-docs.md): optional official RCSB MCP discovery, selected GUI/MCP parity gaps, candidate export and validated pipeline composition. Existing source-only v1 workshop recipes remain an authoring prototype. Concurrent scientific campaigns and unrelated repository edits were preserved.

## What was done

- Added bridge v41 / package 1.16.0: `rcsb_status`, `rcsb_tools`, `rcsb_query`, `rcsb_import_structure`, `candidates_list`, `candidate_export`, `export_read`, `candidates_compare`, `pipeline_catalog`, `pipeline_recipe_plan`, and `iterative_batch_plan`.
- Added the native AI settings installation/repair action for official `rcsb-mcp` 0.15.0. `rcsb-lock.json` pins 32 wheel dependencies and SHA-256 hashes for managed Python 3.11 on Apple silicon. Installation uses an isolated `--target` tree; no model environments or global client registrations are changed. The first qualification attempt showed that portable control Python intentionally lacks `venv`; the supported installation now uses its existing pip with an offline, hash-checked wheel set.
- RCSB requests use its official stdio server and discovered schemas. Upstream query errors are preserved. Dependencies and the recorded interpreter are verified before invocation; bytecode caches cannot supersede verified sources. Worker timeouts stop the process group. Explicit biological-assembly imports save the mmCIF and a separate source receipt with URL, accession, assembly, retrieval timestamp and checksum.
- Added typed engine/scaffold allocation around the existing ProteinHunter planner and shared broker. Each engine receives an equal total trajectory budget; explicit framework allocations retain scaffold-specific CDR ranges. Same-family design/initialization models cannot serve as independent checks. Child outputs remain visible in the native batch hierarchy; checksum completion receipts govern resume.
- Exposed the existing native optional ligand-screening route in ProteinHunter (`ligand_verification`) and RFdiffusion3 (`request.nesso`). Detached preflight preparations preserve native scorer options, verification engine and source dependencies without prematurely creating a campaign. ProteinHunter reads the single SMILES ligand from its actual YAML template. RFdiffusion3 stages the native verification inputs before campaign preparation. Added the already-supported ESMFold2 verifier families to dependency preparation.
- Added exact candidate identities and snapshot-bound cursors. The export path performs a complete bounded CSV scan, avoiding the historical result reader's silent 1,000-row cap. Selected ZIPs include available sequences, structures/confidence files, scores, lineage, source manifests and checksums; missing sequences are explicit. Artifact changes invalidate snapshots. Chunk retrieval supports remote assistants. Threshold summaries preserve predictor/role/context and missing/ambiguous denominators.
- Fixed an existing broker status race exposed by the regression suite: per-job state updates now serialize cancellation and progress, preserve cancellation intent and avoid reopening a terminal job. Worker-start PID updates use the same lock.
- Added executable v2 recipes for supported existing routes. Complete route parameters pass the original planner and the recipe digest is bound into its immutable plan; execution still uses `job_start`, existing scheduling, runtime/code provenance and shared execution lock. This is not an arbitrary graph executor. Imported ProteinHunter templates and RFdiffusion3 structures/conformers now participate in plan provenance checks.
- Exposed the portable operating skill and its references as MCP resources and added the `studio-workflow` prompt. Added output contracts for candidate/export summaries and executable plan tools. Updated README, assistant walkthrough, bridge docs and review; validated the skill using `skill-creator` guidance.

## Results

No performance measurements — implementation and functional qualification only.
No new scientific inference or experimental binding claims.

The isolated official RCSB installation initialized successfully. Live requests returned entry metadata for **4HHB**, mapped **4HHB.A → UniProt P69905** (PDB sequence positions 1–141 to UniProt 2–142), and imported biological assembly **1**. Downloaded mmCIF SHA-256:
`54c2b76cd6f009f0902f11a28162eccb71dd24375e00481639a2d2ec55a2e6e2`.
This checks the public integration, not target suitability for a design experiment.

Passed **110 distinct tests** across MCP (37, including 12 new integration cases),
native engine batches (10), desktop job ownership/recovery (25), native ligand
screening (14), framework results (3) and recipe authoring (21). The 12 new tests
were also rerun after final export-resource and input-checksum assertions.
`swift build` passed, as did the portable-skill validator and scoped diff checks.
The broker tests needed normal macOS process-inspection permission; a sandboxed
attempt correctly deferred execution instead of bypassing its recovery checks.

Verification logs and the public-service response are in [artifacts/0291-mcp-integration](artifacts/0291-mcp-integration/).

## Decision and rationale

Use RCSB's maintained server rather than duplicating its search/GraphQL/mapping interfaces. Keep it optional so online discovery does not become a local-inference dependency. Store an explicit biological assembly rather than choosing the asymmetric unit automatically.

Compile supported workflow routes through their existing planners rather than introduce another scientific execution engine. Keep v1 authoring and v2 execution distinct. Equal budgets, exact input identities and stable recovery matter more than presenting arbitrary connections as validated science.

Use bounded, checksum-verified ZIPs and chunk retrieval rather than giving remote assistants only Mac-local paths. Separate candidate identity from parent hit status and separate model confidence from experimental evidence.

## Reproduce

From the canonical repository, with process-inspection permission for broker tests:

```bash
python3 -B -m unittest discover -s Tests -p 'test_mcp*.py'
python3 -B -m unittest discover -s Tests -p test_iterative_engine_batch.py
python3 -B -m unittest discover -s Tests -p test_desktop_jobs.py
python3 -B -m unittest discover -s Tests -p test_recipe_authoring.py
```

Run `test_ligand_screening.py` and `test_framework_batch_results.py` with a Python environment containing the existing test dependencies (the installed IntelliFold Python was used). Run `swift build` for the native AI settings. The native/bridge tests use temporary fake engines, not actual predictors.

For a separate RCSB qualification runtime, run the source `mcp/research.py install` with managed control Python 3.11 and `NANOHUNTER_ROOT` set to a temporary directory, then `research.py test`. Query the advertised `rcsb_get_entries` and `rcsb_seqcoord_alignments` schemas, and call `rcsb_import_structure` with explicit accession/assembly. The qualification root for this run was `/tmp/iproteinstudio-rcsb-qualification`.

## Limits and what was not tested

- Source implementation and build only: the running installed app was not redeployed, client registrations were not changed and no active campaign was restarted. The native settings button was compiled; its helper was exercised directly in isolation, not clicked in a newly deployed app.
- No new real-model ProteinHunter/RFdiffusion3/NISE campaign, ligand binding experiment, GPU throughput measurement or cloud comparison. Tests establish routing/provenance/recovery contracts, not new scientific performance.
- RCSB public metadata, mapping and assembly download passed; no private queries, alternate macOS/Python architecture, offline mirror or remote mobile UI was tested. The pinned package requires managed Python 3.11 on Apple silicon.
- Candidate scans explicitly stop beyond 20,000 candidates or 20,001 rows in an individual source CSV. Exports accept at most 100 candidates and 64 MiB of source files. Historical records may lack sequences or source manifests; these are not reconstructed by guessing.
- V2 recipes cover existing supported routes, not arbitrary DAGs, GUI drag-and-drop authoring or autonomous engine addition. Scaffold-specific templates and resolved CDR ranges must be supplied. General timing aggregation and legacy-tool output-schema standardization remain outside this change.
- The existing screening-route test fixture lacked the now-required `nanohunter_root`; the fixture was updated to reference repository scripts. No scientific runner behavior was changed for that failure. The recipe name-length error code was preserved after extending shared schema validation to enforce `maxLength`.

## Next

Deploy an updated app through the normal release workflow when appropriate, then qualify the native RCSB installation action and representative newly composed scientific routes with small authorized real-model trials before large campaigns.
