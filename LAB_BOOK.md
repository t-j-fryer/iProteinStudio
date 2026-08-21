# Lab Book

The project's memory. Every experiment, decision, benchmark and non-obvious bug that
shaped this repository is recorded here — including the ones that did not work.

**If you are an AI agent picking up this repository: read [`CLAUDE.md`](CLAUDE.md), then
this file, then any entry it points you at. Recording your own work here is mandatory.**

---

## Current status

_Last updated: 2026-08-21_

| | |
|---|---|
| **Stage** | Alpha. Debug and release builds pass; a standalone managed install has completed acceptance folds; not signed or notarised. |
| **Platform** | macOS 14+, Apple Silicon only. Developed on M4 Max / 64 GB / macOS 26.x. |
| **Repo** | Public — `github.com/t-j-fryer/iProteinStudio` (renamed from NanoHunterStudio) |
| **Runtime** | `~/.iproteinstudio` — **not** Application Support: a space in the path breaks every Python console-script shebang |

**Working:** setup wizard with per-engine choice, worked examples (α-cobratoxin
with its alignment included, and fluorescein), project management, a
prediction-only tab that reuses every alignment on the machine, nanobody/mini-binder/peptide design form,
live metrics dashboard, hits gallery, offline py2Dmol structure viewer with visual controls, target prep,
predictions library, a unified in-app structure/metric browser for completed
Predict, iterative and RFdiffusion3 runs, persistent per-project run history and
a global Activity panel with exact checkpoint Resume for newly recorded iterative campaigns.

**Also working:** Ligand Intelligence — chemistry QA, recognition-core vs linker
separation, conformer ensembles weighed against experimental PDB structures, and a
design budget split across the shapes a molecule actually adopts, with directed
core-to-linker bonds, annotated RFD atom names, reviewed condition suggestions and
stereochemistry-safe PDB evidence; choice of design predictor (Boltz-2 ± potentials,
Protenix v2/Mini, or IntelliFold PyTorch v2-flash/full v2)
with IntelliFold or OpenFold-3 orthogonal checking; measured-optimum scheduling
delegated to NanoHunter's runner; a pinned standalone installation that does not
need a sibling checkout, with explicit reuse of an existing NanoHunter/RFD3
install as an option; an RFdiffusion3 tab that drives the
validated production pipeline, survives quitting the app, resumes protein stages
and small-molecule stages from checkpoints and presents its ranked-result summary.
Protenix uses native MPS with no CPU fallback, owns its upstream public MSA-server
route, and is a removable managed component rather than a hidden Boltz dependency.

**Known gaps, in priority order:**

1. Exact-manifest Resume is implemented, but still needs a deliberate
   interrupt/relaunch/resume acceptance run from GUI controls. Complete RFD3 and
   nanobody routes were exercised through their production entry points rather
   than a heavy GUI click — see [0016](lab_book/0016-complete-campaigns-and-run-recovery.md).
2. Accessibility labels now cover examples, primary Start actions, navigation
   and the active-run banner, but the remaining forms have not had a complete
   VoiceOver, keyboard-focus, large-text or contrast pass.
3. RFdiffusion3's ranked structures are browsable, but it does not yet provide a
   paired apo–holo comparison with preorganisation RMSD and self-consistency.
4. OpenFold-3 complex pLDDT has an unresolved scale problem — see
   [0002](lab_book/0002-inherited-speed-lessons.md) §7.
5. No app icon, no Developer ID signing/notarisation, no self-update.

**Deliberately out of scope:** NISE (experimental, stays in NanoHunter); RFdiffusion3
against DNA/RNA (no `rfd3na` checkpoint obtainable on this machine — see
[0001](lab_book/0001-repository-genesis-and-audit.md) Finding 4).

---

## Where the science lives

Studio is a front end. The implementations it drives originate in sibling
repositories, which remain the development references for scientific behaviour.
They are not runtime dependencies of a standalone install:

- **NanoHunter / iProteinHunter** — `/Users/thomasfryer/NanoHunter` — iterative design
  runner, Boltz-2 / IntelliFold PyTorch / OpenFold-3, MPNN + AntiFold designers,
  MSA handling, device throughput calibration.
- **RFD3** — `/Users/thomasfryer/RFD3` — RFdiffusion3 backbone generation on MLX, ligand
  conditioning, length-binned batching, and the production
  RFD3 → LASErMPNN → Boltz-2 affinity/apo campaign that the RFdiffusion3 tab drives.
  `scripts/design_from_yaml.py` is the entry point; it owns the binder-length
  arithmetic and the atom preflight, and Studio must not duplicate either.

---

## Entries

Newest first.

| # | Date | Entry | What it settles |
|---:|---|---|---|
| 0030 | 2026-08-21 | [Promote the authoritative repo and harden the Protenix install](lab_book/0030-promote-authoritative-repo-and-harden-protenix.md) | Which path is source versus runtime, why the download stalled, verified resume/progress, Protenix v2/Mini integration, native MSA routing and safe engine removal |
| 0029 | 2026-08-20 | [Retire untrusted JAX/Metal predictors and retain IntelliFold PyTorch](lab_book/0029-retire-untrusted-jax-metal-predictors.md) | Why AlphaFold 3 and IntelliFold JAX/Metal are no longer installable or runnable, the fail-loud compatibility boundary, and why IntelliFold PyTorch remains supported |
| 0028 | 2026-08-20 | [Audit AlphaFold 3 Apple-GPU correctness and make prediction sampling explicit](lab_book/0028-audit-af3-apple-gpu-and-prediction-sampling.md) | Same-input evidence that MSA/recycles were correct, why neither current JAX/MPS nor the MLX port is yet a trustworthy AF3 route, GPU-only product policy, durable run MSAs, sampling controls and prediction-library repair |
| 0027 | 2026-08-18 | [Generalize exact-ligand PDB matching beyond one regression molecule](lab_book/0027-generalize-ligand-pdb-matching.md) | Complete paginated CCD search, fail-loud external identity checks, and live validation on caffeine, aspirin, ibuprofen, glucose and acetate |
| 0026 | 2026-08-18 | [Make ligand conditioning explicit, mapped, and stereochemistry-safe](lab_book/0026-fix-ligand-conditioning-and-biotin.md) | Directed core/linker selection, exact RFD atom labels, reviewed chemistry suggestions, correct H-bond semantics, and full-identity biotin PDB evidence |
| 0025 | 2026-08-18 | [Audit ligand conditioning and reproduce the biotin PDB failure](lab_book/0025-audit-ligand-conditioning-and-biotin.md) | What Suggest for me actually does, why biotin returned zero matched structures, the incompatible atom-number systems, and the donor/acceptor direction bug |
| 0024 | 2026-08-18 | [Editable numbers, Richardson cartoons, and the installed-method matrix](lab_book/0024-editable-numbers-richardson-and-method-matrix.md) | Typed numeric controls, the structure-viewer default, actual Apple-GPU versus CPU device use, and the OpenFold shared-MSA basename adapter |
| 0023 | 2026-08-18 | [Fit viewer controls and audit the minimum-window GUI](lab_book/0023-fit-viewer-controls-and-audit-minimum-layout.md) | Why py2Dmol ignored its host width, the responsive canvas/rail contract, workflow-specific hotspot chain labels, and the minimum-window GUI pass |
| 0022 | 2026-08-18 | [Share exact target MSAs and adopt py2Dmol everywhere](lab_book/0022-share-msas-and-adopt-py2dmol.md) | Why target prep differed from Predict, the exact-sequence MSA contract shared by every workflow, and py2Dmol's role versus the retained surface renderer |
| 0021 | 2026-08-17 | [Keep long workflow forms inside the window](lab_book/0021-contain-workflow-forms-to-window.md) | Why RFdiffusion3 expanded beyond the window, and the viewport constraint that keeps navigation fixed while the form scrolls |
| 0020 | 2026-08-17 | [Make checking scope explicit and audit RFD3/Predict](lab_book/0020-audit-rfd3-predict-contracts.md) | Final versus all-cycle orthogonal checking, exact RFD3 sequence/output accounting, resumable plain prediction and fail-loud input validation |
| 0019 | 2026-08-17 | [Unify the iterative GUI and CLI contract](lab_book/0019-unify-iterative-gui-cli-contract.md) | Workflow-specific hotspot restraints, model/option scope, real hit thresholds, final-cycle checking, reproducible seeds and multi-engine result identity |
| 0018 | 2026-08-14 | [Browse prediction and design results in the app](lab_book/0018-browse-run-results-in-app.md) | One offline browser for Predict, iterative and RFdiffusion3 structures; honest cross-engine metric naming; safe shared-batch result matching |
| 0017 | 2026-08-14 | [Constrain Boltz-only prediction options](lab_book/0017-constrain-boltz-only-prediction-options.md) | Why steering and affinity controls follow Boltz selection, ligand eligibility, saved-state normalisation and launch-time sanitisation |
| 0016 | 2026-08-14 | [Complete RFD3 and nanobody campaigns, then make runs recoverable](lab_book/0016-complete-campaigns-and-run-recovery.md) | Full staged protein and nanobody acceptance, protein ranking semantics, exact run manifests, activity/history UI and sleep inhibition |
| 0015 | 2026-08-14 | [Exercise real GUI GPU jobs and audit the app as a product](lab_book/0015-gui-gpu-and-usability-audit.md) | Real MPS/MLX launch evidence, active navigation, two acceptance bugs, and the prioritized usability/accessibility roadmap |
| 0014 | 2026-08-13 | [Promote the standalone runtime and keep workflow navigation available](lab_book/0014-runtime-promotion-and-persistent-navigation.md) | Why navigation stays visible during campaigns, how concurrent starts are blocked, and which validated runtime the GUI uses |
| 0013 | 2026-08-13 | [A standalone install with both IntelliFold v2 models and bundled nanobody MSAs](lab_book/0013-standalone-intellifold-and-scaffold-msas.md) | Managed caches, pinned sources/checkpoints, v2-flash versus full-v2 routing, scaffold alignments, and real isolated-root acceptance runs |
| 0012 | 2026-08-13 | [Worked examples with a shipped alignment, and the first real from-scratch install](lab_book/0012-worked-examples-and-fresh-install.md) | Why the aCbx alignment ships with the app, and what a from-scratch install actually proves |
| 0011 | 2026-08-13 | [Rename to iProteinStudio, per-engine installs, and a clean-clone check](lab_book/0011-rename-and-fresh-user-install.md) | The local paths that were being shipped, per-engine installation, and what a new user actually receives |
| 0010 | 2026-08-13 | [A fresh install was missing the entire RFdiffusion3 script layer](lab_book/0010-shipping-the-rfd3-overlay.md) | Why a clean clone could not run anything, how the overlay ships, and exactly what an update does and does not carry |
| 0009 | 2026-08-13 | [A prediction-only tab, and an alignment cache shared with the design side](lab_book/0009-prediction-tab.md) | Why the MSA cache is the feature rather than the folding, how batches are shaped, and the per-engine schedules |
| 0008 | 2026-08-11 | [Self-contained installation, OpenFold-3 and the IntelliFold JAX backend](lab_book/0008-self-contained-install-and-remaining-backends.md) | Why the old install path could never have worked, the three ways a copied venv stays tied to its origin, and the last two backends |
| 0007 | 2026-08-11 | [Predictor settings audit, corrected speed claims, and ligand-atom targeting](lab_book/0007-predictor-settings-audit-and-ligand-targeting.md) | What each engine actually runs with and whether it is optimal, why the old speed multipliers were inverted, and how Boltz ligand atom names shift under the affinity head |
| 0006 | 2026-08-11 | [Ligand Intelligence — conformer analysis and evidence-based design allocation](lab_book/0006-ligand-intelligence.md) | How a flexible ligand's shapes are found, weighed against the PDB, and turned into a design budget — and three silent failures found doing it |
| 0005 | 2026-08-11 | [Designer routing, predictor roles, install detection, and RFD3 options](lab_book/0005-designer-routing-and-install-detection.md) | Why per-component linking beats all-or-nothing, the missing `--workflow` flag, and which predictors belong in which role |
| 0004 | 2026-08-10 | [RFdiffusion3 tab, rebuilt on the validated production pipeline](lab_book/0004-rfdiffusion3-tab.md) | Why Studio drives the RFD3 repo's scripts instead of its own, and the binder-length-versus-total-length bug that decided it |
| 0003 | 2026-08-10 | [Refresh the vendored pipeline, add AlphaFold 3 and OpenFold-3, expose scheduling](lab_book/0003-predictor-choice-and-scheduling.md) | Predictor choice, what scheduling is delegated rather than reimplemented, and which flags must never be overridden |
| 0002 | 2026-08-10 | [Inherited Apple-Silicon speed lessons](lab_book/0002-inherited-speed-lessons.md) | Every measured performance number Studio's scheduling is based on, and the optimisations that were tried and rejected |
| 0001 | 2026-08-10 | [Repository genesis, code audit, and the Lab Book system](lab_book/0001-repository-genesis-and-audit.md) | Starting state, the stale-pipeline finding, private-repo and SMILES/DNA-scope decisions |

---

## Adding an entry

```bash
cp lab_book/TEMPLATE.md lab_book/00NN-short-slug.md
```

Fill in every section, add a row to the table above (newest first), and update
**Current status** if the work changed it. Sections that do not apply get `n/a` and a
reason rather than being deleted — a missing section is indistinguishable from a
forgotten one.
