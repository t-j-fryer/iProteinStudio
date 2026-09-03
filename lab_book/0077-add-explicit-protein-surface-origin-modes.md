---
entry: 0077
title: Add explicit protein-surface origin modes
date: 2026-09-03
author: gpt-5-codex
type: implementation
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [rfd3, mlx, protein-binder, ori, gui, mcp]
---

## Context

Protein de-novo RFdiffusion3 exposed Foundry's target-COM, hotspot-COM and XYZ
origin controls directly. Calling target COM the no-hotspot/default route was
unsafe for a fixed globular protein: the origin can lie inside the protein, and
one origin cannot mean “search the whole surface.” Empty hotspot selection was
also described as binding anywhere even though it did not implement surface
coverage. This followed the failed mNeonGreen campaign investigation and Entry
0076's separate EMA-weight repair.

## What was done

- Added four semantically separate protein placement modes:
  `surface_scan`, `surface_patch`, `targeted_epitope`, and advanced `manual` XYZ.
  The GUI shows the first three normally and hides manual coordinates in a
  disclosure. Small-molecule COM behavior is unchanged.
- `surface_scan` calculates heavy-atom SASA with Biotite, constructs local
  exposed-residue patches, estimates outward normals with local PCA, rejects
  obstructed centres, and farthest-point samples surface coverage.
- `surface_patch` derives one outward centre from a broad residue selection.
  Its residue set is stored separately and is never serialized as
  `select_hotspots`. Only `targeted_epitope` emits hotspot conditioning.
- Roughly five designs are allocated per surface location. Lengths rotate
  across locations, avoiding a Cartesian explosion of one-design ORI × length
  fixtures while retaining exact total quotas.
- Every ORI becomes an immutable MLX fixture variant. `surface_origins.json`,
  `bin_manifest.json`, `run_manifest.json`, and backbone metrics retain its XYZ,
  surface centre, anchor residues, SASA, clearance, offset, seed and quota.
- Migrated old protein de-novo COM and empty-hotspot saved requests to whole
  surface. Direct preparation and MCP planning reject an explicit protein-COM
  fallback instead of silently weakening it.
- MCP v5 advertises and validates the same four modes. Server guidance now makes
  surface scan the unspecified-site default.

## Results

The distributable containing this work is version 0.2.0, build 14. The DMG is
built from the clean commit after the checks below pass, so its embedded build
number and source provenance distinguish it from the earlier build 13.

The bundled 1YCR MDM2 target was used as a deterministic executable fixture.
No performance conclusion is drawn from these smoke measurements.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| whole-surface plan, 8 requested designs | 2 ORIs | repeated plans identical | yes |
| computed whole-surface ORIs | 2 | minimum target clearance | >= 4.0 Å |
| broad region A50/A54 | 1 ORI | target clearance | 4.05 Å |
| Foundry features-only paired ORIs | 2 | response to +5 Å input-X shift | -5.000, 0.000, 0.000 Å |
| MLX smoke, 60-aa binder, 20 steps, FP32 | 1 | accepted / attempted | 1 / 1 |
| same MLX smoke | 1 | Cα valid geometry | 100% |
| same MLX smoke | 1 | target contacts <= 8 Å / <= 5 Å | 207 / 27 |

The Swift build passed. Four surface-policy/geometry/quota tests, the workflow
pipeline contract, the RFdiffusion3 results/ORI UI contract, all 13 MCP bridge
tests, campaign preparation through the real design-YAML preflight, a real
Foundry features-only fixture, and one real MLX trajectory passed.

## Decision and rationale

“No specified epitope” now means explicit surface coverage, not target COM and
not an empty hotspot request. Broad-region placement remains distinct from
scientific contact conditioning so a user can narrow the search without making
an unsupported residue-contact claim. Per-ORI fixtures were chosen because the
pinned Javier MLX sampler consumes origin-conditioned immutable features; changing
only downstream sampling metadata would not change what the model sees.

The user-requested ORI jitter concept was deliberately not implemented. Random
jitter would blur the meaning and provenance of the four explicit modes.

## Reproduce

```bash
cd /Users/thomasfryer/iProteinStudio
MPLCONFIGDIR=/private/tmp/iprotein-ori-mpl \
  "$HOME/.iproteinstudio/rfd3/.venv/bin/python" Tests/test_rfd3_surface_origins.py
"$HOME/.iproteinstudio/rfd3/.venv/bin/python" Tests/test_workflow_pipelines.py
python3 Tests/test_mcp_bridge.py
bash Tests/test_rfd3_results_ui_contract.sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  CLANG_MODULE_CACHE_PATH=/private/tmp/iproteinstudio-swift15-cache-ori \
  SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/iproteinstudio-swift15-cache-ori \
  swift build
```

The paired Foundry fixtures and MLX smoke artifacts from this session were
written under `/private/tmp/iprotein-ori-foundry.GFkZPv`; they are disposable,
not source-controlled evidence.

## Limits and what was not tested

- The MLX acceptance used one 20-step trajectory. It proves execution,
  conditioning transfer and basic geometry, not binder quality or enrichment.
- Full 200-step surface campaigns, multiple protein topologies, very large or
  concave assemblies, multichain interfaces, and experimental hit enrichment
  were not tested.
- Farthest-point selection uses Euclidean patch-centre separation rather than a
  triangulated solvent-surface geodesic.
- The GUI was compiled and its source contract tested, but the four controls
  were not manually clicked through with VoiceOver.
- Manual XYZ validates shape/finite values but remains an expert responsibility;
  unlike generated modes it is not automatically moved to the nearest safe
  solvent-facing centre.

## Next

Run a controlled 200-step comparison on at least one globular target: old
target-COM (diagnostic only), whole-surface, broad-region, and targeted-epitope.
Compare valid-fold rate, interface contacts and independent complex/apo recovery
by ORI before changing the five-designs-per-location policy.
