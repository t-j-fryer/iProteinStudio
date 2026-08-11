---
entry: 0001
title: Repository genesis, code audit, and the Lab Book system
date: 2026-08-10
author: claude-opus-5
type: audit
status: complete
machine: Apple M4 Max, 40-core GPU, 64 GB unified memory, macOS 26.x
tags: [meta, repo, audit, install]
---

## Context

NanoHunter Studio existed only as an untracked local directory. It was designated the
app-based front end to the whole Apple-Silicon protein design suite, with the design
tools themselves developed in sibling repositories. Before adding features, the project
needed version control, a home on GitHub, and a durable way to record *why* things were
done — so that any agent or person inheriting the work starts informed rather than
guessing. This entry records the starting state and the ground rules.

## What was done

**Version control.** `git init` on `/Users/thomasfryer/NanoHunterStudio`, baseline commit
of the existing alpha, and a **private** repository created at
`github.com/t-j-fryer/NanoHunterStudio`. The existing `.gitignore` already excluded
`.build/`, `build/`, `Package.resolved`, and Xcode artefacts; no weights or model files
were present in the tree.

**Lab Book system.** `LAB_BOOK.md` (index plus current status), `lab_book/TEMPLATE.md`,
and one file per entry under `lab_book/`. `CLAUDE.md` states the standing requirements
and makes recording work mandatory for any AI touching the repo.

**Audit** of the app and its three sibling sources — findings below.

## Results

*No measurements — audit and repository setup only.*

### The app as inherited

SwiftUI app built with SwiftPM (`swift-tools-version:5.9`, macOS 14+), ~3,600 lines of
Swift across 30 files. `swift build` passes clean in ~50 s. Structure is a genuine
UI-agnostic core with SwiftUI on top:

- `Core/` — `AppPaths`, `ScaffoldCatalog`, `TemplateWriter`, `CommandBuilder`,
  `ProcessRunner`, `RunController`, `MetricsWatcher`, `PipelineInstaller`,
  `CalibrationRunner`, `TargetPredictor`, `CDRDetector`, `PredictionStore`,
  `ThumbnailStore`, `SmilesThumbnailStore`, `SystemMemory`
- `Views/` — setup wizard, projects sidebar, design form, live dashboard (Swift Charts),
  hits gallery, structure viewer (offline 3Dmol.js in `WKWebView`), target prep,
  predictions library
- `Resources/pipeline/` — a **vendored copy** of the NanoHunter runner and assets, staged
  into `~/Library/Application Support/NanoHunterStudio/` on first run

The vendoring design is sound: the app is independent of the NanoHunter source tree at
runtime, installs into managed Application Support, and never touches the user's home
directory layout.

### Finding 1 — the vendored pipeline is badly stale (the important one)

| | Lines | Last modified |
|---|---:|---|
| `Sources/.../Resources/pipeline/nanohunter_run.sh` | 5,823 | 2026-07-20 |
| `/Users/thomasfryer/NanoHunter/nanohunter_run.sh` | 7,073 | 2026-08-10 |

The app ships a runner that is three weeks and 1,250 lines behind upstream. Everything in
`lab_book/0002-inherited-speed-lessons.md` — the IntelliFold JAX backend, AlphaFold 3 and
OpenFold-3 support, `--design-scheduler cycle-wave`, `--wave-batch-size`,
`--throughput-profile`, `--resume`, token bucket flags — postdates the vendored copy.
**The app currently cannot express any of the optimisation work, because the script it
drives does not have the flags.** This is the root cause blocking most of the requested
feature set, and it is fixed first.

### Finding 2 — the app hard-codes a two-predictor pipeline

`CommandBuilder.arguments` emits a literal `--predictor boltz --post-predictor
intellifold`, and `ARCHITECTURE.md` states OpenFold is "intentionally excluded". The
`DesignRequest` model has no predictor field at all. Adding AF3/OpenFold-3 therefore
means new model state, not just a new picker.

### Finding 3 — RFD3 is a sibling repo with real integration constraints

`/Users/thomasfryer/RFD3` extends `javierbq/rfd3-mlx` @ `a871ccf`. Relevant constraints:

- **Licence.** The upstream MLX port had no explicit licence at checkout. Redistribution
  of derived code is unresolved.
- **The MLX featurizer is protein-only.** Ligand features are generated once through the
  official PyTorch Foundry pipeline and exported as a fixture `.npz`; MLX then samples
  from that fixture. Any new target must pass through Foundry featurisation first.
- **Two known Foundry pitfalls, already fixed upstream in that repo:** a generic `LIG`
  PDB resolves against a three-atom placeholder CCD component (hence explicit CCD
  generation), and supplying both `select_buried` and `select_exposed` caused the later
  selection to erase the earlier one (patched by `scripts/patch_foundry_rasa.py`). Use
  `"ALL"`, not `""`, to fix all ligand atoms in this pinned build.
- **`scripts/run_dtf401_campaign.py` is the pipeline to mirror**, not the two-target
  README walkthrough. Its stages — ligand → fixtures → backbones → mpnn → predict-holo →
  score → predict-apo → rmsd — are each independently resumable, and
  `build_length_bins.py` already implements binned length sampling with shape-homogeneous
  batches, which is exactly the intra-batch-same / inter-batch-different behaviour Studio
  wants.
- **The conditioning flag is `is_non_loopy`**, not `is_not_loopy`
  (`rfd3/inference/input_parsing.py:191`). Worth stating because the wrong spelling
  passes silently — the pinned `rfd3` build sets `extra="forbid"`, so it would raise,
  but `rfd3na` sets `extra="allow"` and would swallow it.

### Finding 4 — DNA/RNA is not actually available

The `rfd3na` nucleic-acid package is installed in `/Users/thomasfryer/RFD3/.venv`, but:
no `rfd3na` checkpoint exists on this machine, `install_rfd3.sh` never fetches one, the
repo's own code imports only `rfd3`, and the installed checkpoint
(`rfd3_foundry_2025_12_01_remapped`, 168,038,994 parameters) is the protein+ligand model
with no nucleotide tokens in `rfd3/constants.py`. The validated MLX fast path is
protein+ligand only.

## Decision and rationale

**Private repository.** The tree will reference RFD3-derived work whose upstream licence
is unresolved, and the suite touches AlphaFold 3 weights governed by Google's terms.
Private matches the sibling repos (`iProteinHunter`, `ProteinHunter2`). Public is
reachable later; un-publishing indexed code is not.

**One file per Lab Book entry, indexed from `LAB_BOOK.md`.** A single append-only file
would grow past the point where an inheriting agent can read it, and would conflict on
every concurrent branch. Numbered files stay greppable and individually citable. Rejected:
GitHub Issues/Discussions (not available offline, not in the clone, invisible to an agent
reading the repo) and per-commit messages alone (they record *what*, poorly, and never
the negative results).

**DNA/RNA dropped from scope for now** — owner's decision after Finding 4 was presented.
The alternatives offered were to wire up `rfd3na` (blocked on weights that may not be
publicly obtainable, and would run on the slow PyTorch path with no MLX speedup) or to
ship the UI gated. Neither justified the cost against a capability nobody can currently
run. RFD3 in Studio covers **protein and small-molecule targets**.

**SMILES handling: support both input routes.** RFD3 has no native SMILES field — there
is no `smiles` key anywhere in `rfd3/inference/input_parsing.py`, so "pass SMILES
natively to RFD3" is not available regardless of preference. The user may paste SMILES
(RDKit ETKDG conformer → explicit CCD component + chain-L PDB, Boltz atom-naming
convention) *or* supply their own PDB/CIF and name the ligand residue. The generalised
implementation already exists as `RFD3/scripts/prepare_ligand_target.py`; Studio drives
it rather than reimplementing RDKit work in Swift. Ligands go on chain L because Foundry
reserves chain A for the diffused binder and errors on overlap.

## Reproduce

```bash
cd /Users/thomasfryer/NanoHunterStudio
swift build                      # ~50 s, clean
./build_app.sh                   # assembles build/NanoHunter Studio.app

# Confirm the staleness finding
wc -l Sources/NanoHunterStudio/Resources/pipeline/nanohunter_run.sh \
      /Users/thomasfryer/NanoHunter/nanohunter_run.sh

# Confirm rfd3 has no SMILES field and the flag spelling
grep -rn "smiles" /Users/thomasfryer/RFD3/.venv/lib/python3.12/site-packages/rfd3/inference/input_parsing.py
grep -n  "loopy"  /Users/thomasfryer/RFD3/.venv/lib/python3.12/site-packages/rfd3/inference/input_parsing.py
```

## Limits and what was not tested

- The app was built but **not launched or exercised** during this audit. No claim is made
  that the existing dashboard, installer, or run orchestration work end to end; only that
  they compile.
- The vendored/upstream runner comparison is by line count and modification date. The
  1,250-line delta was not reviewed hunk by hunk.
- Sibling-repo behaviour was read from source and documentation, not re-executed.

## Next

Refresh the vendored pipeline (Finding 1) before anything else — it gates the predictor
and scheduling work. Then predictor selection, then the RFD3 tab.
