---
entry: 0005
title: Designer routing, predictor roles, install detection, and RFD3 options
date: 2026-08-11
author: claude-opus-5
type: bugfix
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [ui, install, predictors, rfd3, mpnn]
---

## Context

Round of corrections after the owner used the app. Six separate problems, one of
which had a non-obvious cause.

## Results

### 1. "AlphaFold 3 and OpenFold-3 are not installed" — correct, and useless

The app was telling the truth. Its managed root
(`~/Library/Application Support/NanoHunterStudio`) held **its own** partial
install from July — Boltz, LigandMPNN, AntiFold, IntelliFold — with no AF3, no
OpenFold-3, no LASErMPNN. The full set lives in `/Users/thomasfryer/NanoHunter`,
which the app was not using.

The `--link-existing` path I wrote in [[0003-predictor-choice-and-scheduling]]
would have fixed it but was too blunt: it symlinked `venvs/`, `src/` and
`models/` **wholesale**, moving any existing directory aside. On this machine
that would have orphaned four working environments and several GB, to gain three
missing ones.

Linking is now **per component**:

```
keep      venvs/NanoHunter_boltz (already installed here)
link      venvs/NanoHunter_openfold3_mlx
link      venvs/NanoHunter_alphafold3
link      venvs/NanoHunter_lasermpnn
link      src/alphafold3
link      models/alphafold3
```

After running it against the real root, all eight components report `ok`,
including AlphaFold 3 **with weights** and the IntelliFold JAX flash model.

The general lesson, which is why this is an entry rather than a commit message:
**"reuse an existing install" is not one decision, it is one per component.** A
machine can be half-installed in either direction, and an all-or-nothing link
forces a destructive choice that neither state deserves.

### 2. LigandMPNN was offered against protein targets

It is ligand-aware and has nothing to condition on without a ligand. Removed.
`allowedDesigners` for a de-novo binder is now `[proteinmpnn, solublempnn]` for a
protein target and `[ligandmpnn, lasermpnn]` for a small molecule.

### 3. LASErMPNN was missing for ligand targets

Now offered in both tabs. It has a pretrained ligand encoder and decodes
side-chain rotamers jointly with the sequence, which tends to over-pack the
binding site less than LigandMPNN. It runs on **CPU** — `torch-scatter` and
`torch-cluster` have no MPS kernels — and the UI says so, because a user watching
GPU load would otherwise think it had stalled.

### 4. `--workflow` was never passed (latent, and worse than the visible bugs)

`CommandBuilder` never emitted `--workflow`, so every run used the runner's
default of `nanobody`. Ligand-aware designers are rejected outside protein
workflow, so a de-novo mini-binder run could not have used LigandMPNN or
LASErMPNN at all — the option would have been accepted by the UI and refused by
the runner. Now passed explicitly from `DesignRequest.workflow`.

This was found while adding LASErMPNN, not by testing. It is the same class of
mistake as the RFD3 length bug in [[0004-rfdiffusion3-tab]]: a default that is
correct for the original case and silently wrong for the new one.

### 5. OpenFold-3 in the wrong role

It was offered as a **design engine** and, because the check list was built from
`designChoices`, appeared as a checker only by accident — and disabled, because
of (1). Now:

- `Predictor.designChoices` — Boltz-2, Boltz-2 + potentials, IntelliFold, AF3.
  OpenFold-3 is deliberately excluded: it was the weakest driver in the campaign
  comparison and costs ~2.5× Boltz per design.
- `Predictor.checkChoices` — all five.

Its complex-pLDDT scale caveat is removed from the UI. The underlying issue is
unresolved and still recorded in [[0002-inherited-speed-lessons]] §7; the right
place for it is the Lab Book, not a warning next to a checkbox the user cannot
act on.

### 6. MPNN temperature was not controllable

Now exposed in both tabs, defaulted to the pipeline's own values rather than to
something invented:

| Control | Default | Route |
|---|---:|---|
| First redesign cycle | 0.30 | `--ligand-temp-cycle1` |
| Later cycles | 0.10 | `--ligand-temp-other` |
| LASErMPNN sequence | 0.10 | `LASERMPNN_SEQ_TEMP` |
| LASErMPNN binding site | 1.00 | `LASERMPNN_FS_TEMP` |
| RFdiffusion3 inverse folding | 0.10 | `--temperature` / `--seq-temp` |

The runner aliases the AntiFold and MPNN temperature flags onto the same pair, so
one control legitimately covers every designer except LASErMPNN, which is only
reachable through the environment.

### 7. RFdiffusion3 options

- **Inverse folder is a choice**: LASErMPNN or LigandMPNN for ligands,
  SolubleMPNN or ProteinMPNN for proteins.
- **Verification**: Boltz is always used and labelled as such — it is the only
  backend with an affinity head, and the ranking metric needs P(bind). Potentials
  and the affinity head are explicit toggles. The affinity head is hidden for
  protein targets, because it is trained on small molecules.
- **Protein targets are now end to end**: predict the target structure from a
  sequence inside the tab, view it, click hotspots straight into conditioning;
  then the campaign generates the target MSA once through the MSA server and
  reuses it by path for every fold.

### Verification performed

GPU-free — the dTF140 production campaign was folding throughout.

| Check | Result |
|---|---|
| Per-component link against the real managed root | 8/8 components `ok`, 4 existing kept |
| Ligand campaign with LigandMPNN, no potentials, IntelliFold second opinion | prepares, preflight passes, all new keys in `campaign.json` |
| Protein campaign with hotspots B67/B69/B71 | prepares, preflight resolves all three residues |
| `fixed_motif_residue_count("60-120,/0,B1-71")` | 71 → 60-aa binder gives Foundry total **131**, matching the validated aCbx fixture |
| `swift build`, `./build_app.sh` | clean |
| dTF140 unaffected | still alive, 1,000 backbones done, now in `predict-holo` |

## Decision and rationale

**Every new orchestrator key defaults to the previous behaviour.**
`run_rfd3_nise_campaign.py` was extended while a campaign was running against it.
Python does not re-read the main module, so the live process was safe regardless;
but a config written before these options existed must still behave identically
if it is ever resumed, so `sequence_model` defaults to `lasermpnn`,
`use_potentials` and `run_affinity` to true, `extra_predictors` to empty. Verified
against the live dTF140 config: every key is absent and resolves to its original
value.

**AlphaFold 3 and OpenFold-3 are shown but disabled as RFdiffusion3 checkers,
with the reason stated.** `RFD3/scripts/run_predictors.py` implements Boltz and
IntelliFold only. The alternative was to hide them, which would leave the user
wondering why the list differs between tabs, or to wire them up — AF3 is tractable
via `alphafold3_adapter.py`'s `to-json`/`from-out` pair, OpenFold-3 needs query
JSON construction and A3M rewriting. Neither could be tested with the GPU busy, so
shipping them untested would have been worse than saying so. This is the top item
in Next.

**The apo re-fold toggle is hidden for protein targets** rather than shown and
ignored, because it is only implemented in the small-molecule pipeline.

## Reproduce

```bash
# Per-component link (non-destructive; re-runnable)
SUP="$HOME/Library/Application Support/NanoHunterStudio"
NANOHUNTER_ROOT="$SUP" bash "$SUP/setup_pipeline.sh" \
  --link-existing /Users/thomasfryer/NanoHunter --link-rfd3 /Users/thomasfryer/RFD3
NANOHUNTER_ROOT="$SUP" bash "$SUP/setup_pipeline.sh" --detect

# The length arithmetic that must never regress
cd /Users/thomasfryer/RFD3
.venv/bin/python -c "
import sys; sys.path.insert(0,'scripts')
from design_from_yaml import fixed_motif_residue_count as f
print(f('60-120,/0,B1-71'))   # 71  -> 60-aa binder needs total 131
print(f(None))                # 0   -> ligand campaigns: total == binder length
"
```

## Limits and what was not tested

- **No campaign was run.** Everything here is preparation, validation and UI. The
  GPU was busy with dTF140 throughout, and benchmarking or sampling against a
  live production campaign would corrupt both.
- The **protein RFdiffusion3 path is still untested end to end.** It now has MSA,
  prediction and scoring stages, but none of them has executed. The MSA stage in
  particular (`csv_to_a3m`) parses Boltz's raw MSA CSV by column-name guess and
  has never seen a real file.
- LASErMPNN in the **iterative** tab is wired but unexercised; the runner's
  `--sequence-designer lasermpnn` path was read, not run.
- The predictor-template placeholder for protein verification uses a poly-glycine
  binder of the maximum bin length. `prepare_predictor_inputs.py` overwrites
  chain A per design, so the placeholder should never reach a model — but that is
  reasoned from reading it, not observed.
- Temperature ranges in the UI (0.05–1.0, and 0.1–2.0 for the binding site) are
  chosen for usability, not from any sweep. There is no evidence here about which
  values are good.

## Next

1. Wire AlphaFold 3 into `RFD3/scripts/run_predictors.py` via
   `alphafold3_adapter.py`, then OpenFold-3, so the RFdiffusion3 checker offers
   the same set as the iterative tab.
2. Run the protein RFdiffusion3 path once, small, end to end — it is the largest
   untested surface in the repo.
3. Run one small campaign through each tab and record real timings. Studio still
   has no measurements of its own; this has now been the top gap for three entries.
