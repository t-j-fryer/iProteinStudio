---
entry: 0037
title: Normalize Protenix unknown-residue handoffs
date: 2026-08-25
author: codex-gpt-5.6
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [protenix, iterative-design, solublempnn, correctness]
---

## Context

Protenix represents masked protein positions as `UNK` residues containing the
alanine atom set (`N`, `CA`, `C`, `O`, `CB`) plus a generic `CG` pseudo-atom.
Studio's iterative runner previously replaced every standalone `UNK` token in the
mmCIF text but retained every atom. An alanine substitution therefore produced a
chemically invalid `ALA-CG` handoff. Boltz and IntelliFold unknown residues do not
carry this additional atom.

The problem was discovered after a beta compute-allocation campaign had completed.
That campaign used SolubleMPNN, so it was also necessary to determine whether the
bad side-chain record could have changed the generated sequences rather than only
the saved intermediate structure.

## What was done

- Added
  `Sources/iProteinStudio/Resources/pipeline/scripts/normalize_unk_cif.py`, a
  row-aware mmCIF normalizer for the Protenix v2 and Mini handoff routes.
- Limited the repair to the requested binder chain. For each Protenix `UNK`, the
  normalizer removes `CG`, preserves `N/CA/C/O/CB` and terminal `OXT`, renames the
  residue to `ALA`, and updates the corresponding polymer and bond metadata.
- Made unexpected atoms and incomplete alanine atom sets hard errors. The runner
  will not silently manufacture a chemically ambiguous handoff.
- Passed predictor identity and binder-chain identity from every cycle-zero
  inverse-folding route in `nanohunter_run.sh`.
- Retained the pre-existing substitution behavior for Boltz and IntelliFold,
  whose outputs do not contain the Protenix pseudo-atom.
- Added a mixed-chain executable contract to `Tests/test_workflow_pipelines.py`.
  It verifies the Protenix repair, chain isolation, polymer metadata, rejection of
  an unexpected side-chain atom, and unchanged non-Protenix behavior.
- Audited the installed LigandMPNN implementation used by Studio. Its PDB parser
  builds `X` from `N/CA/C/O`, and the `soluble_mpnn` model uses
  `ProteinFeatures`, which consumes only that four-atom tensor and reconstructs
  its own virtual `CB`. The retained or removed input `CG` is not a SolubleMPNN
  feature.

## Results

| Condition | n | Metric | Value |
|---|---:|---|---:|
| Synthetic mixed-chain Protenix contract | 1 CIF | requested-chain UNKs repaired | 1 |
| Synthetic mixed-chain Protenix contract | 1 CIF | requested-chain CG atoms removed | 1 |
| Synthetic mixed-chain Protenix contract | 1 non-target chain | non-target UNKs changed | 0 |
| Saved Protenix v2 artifact | 1 CIF | UNKs repaired / CG atoms removed | 38 / 38 |
| Saved Protenix v2 artifact after repair | 1 CIF | atom-table `ALA-CG` rows / standalone `UNK` tokens | 0 / 0 |
| Saved Protenix v2 artifact | 300 backbone atoms | `N/CA/C/O` coordinate equality before versus after repair | exact |
| Repaired saved artifact | 1 CIF | Gemmi parse | pass |
| Workflow pipeline contract suite | 1 run | result | pass |

No runtime or throughput measurements were made; this was a handoff-correctness
change.

## Decision and rationale

Protenix handoffs are normalized to alanine regardless of the legacy placeholder
mixture because their retained atom inventory is specifically an alanine. Keeping
`CG` would produce an invalid residue; changing the residue to glycine or serine
would instead leave an incompatible `CB`. A predictor-specific repair is therefore
safer than another text-wide substitution.

Historical campaign outputs are not rewritten automatically. The installed
SolubleMPNN path ignores side-chain input atoms and the repair leaves all of its
actual `N/CA/C/O` inputs unchanged. The completed beta campaign therefore has no
technical indication that it needs restarting. This conclusion is a source- and
coordinate-path audit, not a regenerated-sequence comparison.

## Reproduce

```bash
/Users/thomasfryer/.iproteinstudio/venvs/NanoHunter_boltz/bin/python \
  /Users/thomasfryer/iProteinStudio/Tests/test_workflow_pipelines.py

python3 \
  /Users/thomasfryer/iProteinStudio/Sources/iProteinStudio/Resources/pipeline/scripts/normalize_unk_cif.py \
  --input /Users/thomasfryer/.iproteinstudio/projects/untitled_design/prediction_runs/prediction-20260821-131503/protenix-v2/bucket_128/chunk_0/Hallucinate/pred_min/model_0.cif \
  --output /tmp/iproteinstudio-protenix-handoff.cif \
  --predictor protenix-v2 \
  --binder-chain A \
  --mode ala

bash -n \
  /Users/thomasfryer/iProteinStudio/Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh

cd /Users/thomasfryer/iProteinStudio
swift build
```

## Limits and what was not tested

- The original beta campaign files were not mutated or regenerated, and sequence
  identity was not re-measured by running SolubleMPNN twice. The no-rerun decision
  rests on exact equality of all 300 real-artifact backbone inputs plus the
  installed model's explicit backbone-only feature path.
- The available saved artifact was a Protenix v2 result with 38 unknown residues,
  not the 40-position beta input. Protenix Mini is covered by the same code and
  synthetic contract but was not represented by a separate saved artifact.
- No LigandMPNN side-chain-context, LASErMPNN, or AntiFold numerical output was
  compared before versus after this repair. Those future handoffs now receive the
  chemically valid structure.
- Non-Protenix random placeholder selection remains the historical behavior and
  was outside this bug fix.

## Next

Retain an anonymized Protenix fixture in the test suite if a future upstream
release changes its masked-residue atom representation. Such a change should fail
the atom-inventory contract before a design campaign starts.
