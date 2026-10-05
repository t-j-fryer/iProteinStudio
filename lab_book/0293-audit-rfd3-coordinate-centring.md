---
entry: 0293
title: Audit RFD3 coordinate centring and repair motif atom selection
date: 2026-10-03
author: Codex
type: bugfix
status: complete
machine: Apple Silicon (arm64), macOS 26.6.1; CPU preprocessing only
tags: [rfd3, motif, coordinates, provenance, regression]
---

## Context

The user supplied a report of explicit `infer_ori_strategy="com"` including finite
zero scaffold placeholders before centring in another RFD3 installation. Its
reported offsets and clash rates are external observations, on unspecified
hardware, and were not reproduced as backbone-generation measurements here.
This audit follows the mode implementation in [[0066-add-rfd3-partial-motif-and-dual-validation]]
and the broader [[0132-audit-and-harden-rfd3-pipeline]].

## What was done

Ran the managed installation's `setup_pipeline.sh --detect`: RFD3 was available
with verified EMA assets. Inspected repository GUI/MCP preparation, the installed
Foundry parser/origin functions, the checkpoint's inference transform configuration,
and the feature-only oracle and MLX sampler. No scientific jobs were launched.

Added `Tests/test_rfd3_coordinate_centring.py`. It emits real Studio specs using
the bundled p53–MDM2 example, runs installed `DesignInputSpecification` and the
checkpoint-configured **complete inference preprocessing pipeline**, then inspects
`coord_atom_lvl_to_be_noised` and its fixed/unindexed masks. The checkpoint is
memory-mapped only for its transform configuration; no model is constructed.
The batch-size override is one, matching Studio's feature-only oracle. Tests
capture coordinates immediately before centring as well as after preprocessing.

Tested 200/300 generated residues, untranslated inputs and joint translation
`[300, -180, 120] Å`, omitted origin, explicit all-atom COM, and explicit selected
reference-motif origin. Partial diffusion is tested separately with the bundled
13-residue source peptide, `partial_t=1.0`. The comparisons account for atom14
virtual atoms and removal of terminal OXT; all 112 retained real source-peptide
atom coordinates survive the same joint translation as the fixed target.

A separate defect surfaced in `scripts/patch_foundry_rasa.py`: its preservation
of earlier annotation values applied to **every annotation**, including fixed
coordinates whose default is True. Consequently a request for nine motif atoms
fixed all 33 atoms of those three motif residues. Narrowed preservation to
`rasa_bin`, restoring upstream reset semantics for coordinate and sequence
selections. The patch migrates both unpatched and previously patched pinned source,
is idempotent, and rejects unknown source. Added executable patch tests and exact
post-preprocessing motif-count assertions. Updated overlay provenance. Added
comments and a lightweight assertion preserving the existing motif origin policy.

Applied the patch only to an isolated temporary copy of the installed Foundry
Python package. Its source was verified to equal the shipped patch applied to the
installed source. **The active managed runtime was not edited or deployed.**
Portable runtimes are immutable; carrying this into normal app execution requires
a newly qualified runtime identity, not editing its installed site-packages.

## Results

Functional coordinate measurements, not performance or design-quality benchmarks.
Raw logs, hashes, resolved transform settings and case measurements are in
[artifacts/0293-rfd3-coordinate-centring](artifacts/0293-rfd3-coordinate-centring).
Both installed and corrected copies ran 14 preprocessing cases. The installed
baseline explicitly permits the known expanded-mask defect for diagnosis and
reports `PASS_CENTRING_ONLY_KNOWN_MASK_BUG`; the corrected copy requires nine atoms.

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Installed default, lengths 200/300 | 2 translation pairs | Maximum absolute change in any fixed-coordinate component after translating input | 0.000130 Å |
| Installed explicit COM, length 200 | 1 translation pair | Displacement of fixed-atom centroid caused by translating input | 212.809 Å |
| Installed explicit COM, length 300 | 1 translation pair | Same displacement | 247.899 Å |
| Corrected patch, default, lengths 200/300 | 2 translation pairs | Maximum absolute fixed-coordinate component change | 0.000126 Å |
| Corrected patch, explicit motif origin, lengths 200/300 | 2 translation pairs | Maximum absolute fixed-coordinate component change | 0.000023 Å |
| Selected motif atom count, installed → corrected | 12 motif cases per copy | Requested nine atoms vs actual fixed unindexed atoms | 33 → 9 |

All invariance comparisons use 0.002 Å tolerance for PDB/float32 precision.
Both safe origin policies preserve fixed coordinates across scaffold lengths.
Explicit COM matches the placeholder-weighted analytic offset in both copies.
For example, installed explicit-COM fixed-centroid residual norms on the translated
structure were 230.516 Å (200 residues) and 268.523 Å (300). These are this audit's
example and translation, not the user's external 162/198 Å cases.

The corrected default centres 705 target atoms plus nine motif atoms. The selected
motif centroid remains **7.129 Å** from that joint origin in this example; explicit
selected-motif origin reduces it to numerical zero. This establishes the different
semantics, not a measured quality advantage of either policy.

Other validation: three patch migration/semantics tests PASS; mode/dual-RMSD
contracts PASS; bundled partial/motif preparation/preflight PASS; motif recovery
scoring contracts PASS. `swift build` PASS with writable temporary caches and
`--disable-sandbox` (SwiftPM's nested sandbox failed under the tool sandbox).
Initial diagnostic harness failures concerned comparing selected vs expanded
motif centroids and averaging atom14 virtual atoms; final tests correct those
assumptions and inspect retained real coordinates explicitly.

## Decision and rationale

1. **No placeholder-COM regression in Studio's normal motif path.**
   `prepare_campaign.write_design_yaml()` only emits origin overrides for de novo
   mode. MCP motif plans additionally remove both origin fields. The installed
   Foundry default averages only `is_motif_atom_with_fixed_coord`, excluding generated
   zeros. Its explicit COM implementation instead averages all finite coordinates
   after placeholder insertion, exactly reproducing the reported mechanism.
2. **Keep centring policy unchanged for this audit.** Default fixed centring includes
   the target as well as motif. Explicit motif-only origin is clearer for the user's
   described intended placement, but constitutes a separate deliberate scientific
   setting, requiring end-to-end qualification before promotion. Studio currently
   strips manual origin fields in motif mode; supplying one to its current request
   API does not select a motif-only origin. Do not represent it as supported yet.
3. **Repair the over-broad RASA patch.** Restoring exact selected-atom conditioning
   is a correctness fix, independent of origin placement. Preserve disjoint RASA
   values only, rather than removing the RASA fix or accepting whole-residue masks.
4. **Preserve partial diffusion's own origin.** Its default uses the real diffused
   region's centre and retains source scaffold coordinates. Do not substitute
   motif/target centring or zero those real coordinates.

An adjacent low-level `prepare_ligand_target.py` helper still emits `com` in its
base JSON. Studio's normal campaign YAML is written separately. No small-molecule
workflow or existing ligand campaign was qualified or changed by this motif audit.

## Reproduce

From the canonical repository, with the managed RFD3 installation present:

```bash
export ROOT="$HOME/.iproteinstudio"
bash "$ROOT/setup_pipeline.sh" --detect
export MPLCONFIGDIR=/tmp/iprotein-mpl
"$ROOT/rfd3/.venv/bin/python" Tests/test_rfd3_coordinate_centring.py \
  --allow-expanded-motif --report /tmp/rfd3-installed-centring.json

# Isolate the installed Python package; no weights are copied.
candidate="$(mktemp -d /tmp/iprotein-foundry-centre-XXXXXX)"
cp -R "$ROOT/rfd3/.venv/lib/python3.12/site-packages/rfd3" "$candidate/rfd3"
"$ROOT/rfd3/.venv/bin/python" \
  Sources/iProteinStudio/Resources/rfd3_overlay/scripts/patch_foundry_rasa.py \
  --source "$candidate/rfd3/inference/input_parsing.py"
PYTHONPATH="$candidate" "$ROOT/rfd3/.venv/bin/python" \
  Tests/test_rfd3_coordinate_centring.py --report /tmp/rfd3-corrected-centring.json
"$ROOT/rfd3/.venv/bin/python" -m unittest discover -s Tests -p test_rfd3_rasa_patch.py
"$ROOT/rfd3/.venv/bin/python" Tests/test_rfd3_partial_validation.py
"$ROOT/rfd3/.venv/bin/python" Tests/test_rfd3_worked_examples.py
"$ROOT/rfd3/.venv/bin/python" Tests/test_rfd3_motif_scoring.py
CLANG_MODULE_CACHE_PATH=/tmp/iprotein-centre-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/tmp/iprotein-centre-swift-cache \
swift build --disable-sandbox --cache-path /tmp/iprotein-centre-spm-cache
```

Local source SHA256 values are in the two reports and `provenance.json`. Installed
runtime resolves to `components/rfd3/versions/c9fc19327d6b15b5a14b-20260926T190018Z-0699f078/sources/RFD3`.
The shipped requirement pins Foundry fork commit
`a24335323b8fe8a927319d47b10f5bffffc17969`; hashes, rather than that requirement alone,
identify the actually inspected patched source. The upstream
[inference utilities](https://github.com/RosettaCommons/foundry/blob/production/models/rfd3/src/rfd3/utils/inference.py)
were also consulted; that moving branch is not the installed-source authority.

## Limits and what was not tested

No neural inference, relaxation, structural validation predictions, clash rates,
binding scores, biological efficacy, or performance measurements. No arbitrary
large target, target F complex from the user's report, ligand, symmetric assembly,
other motif macros, or other partial-diffusion noise levels. Translation tests
check conditioning geometry, not bit-identical stochastic generated backbones.
No model weights changed, copied, committed or redistributed. The active runtime
still has the expanded-mask defect pending a qualified runtime update. No commit
or release created; pre-existing unrelated workspace changes were preserved.

## Next

Build a new managed runtime containing the RASA-only patch, then run a 1–5-backbone
MCP preflight/job smoke test for motif and partial workflows before promotion.
If adding motif-only origin as a Studio setting, derive it from selected real
reference atoms, save the chosen origin, preserve the shared target/motif frame,
and keep these final-conditioning checks. Evaluate design quality separately.
