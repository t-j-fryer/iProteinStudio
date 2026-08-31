# Lab Book

The project's memory. Every experiment, decision, benchmark and non-obvious bug that
shaped this repository is recorded here — including the ones that did not work.

**If you are an AI agent picking up this repository: read [`CLAUDE.md`](CLAUDE.md), then
this file, then any entry it points you at. Recording your own work here is mandatory.**

---

## Current status

_Last updated: 2026-08-31_

| | |
|---|---|
| **Stage** | Alpha. Debug and release builds pass; a standalone managed install has completed acceptance folds. Signed-update code and release automation are implemented, but no Developer ID certificate is installed and no notarised public build has shipped. |
| **Platform** | macOS 14+, Apple Silicon only. Developed on M4 Max / 64 GB / macOS 26.x. |
| **Repo** | Public — `github.com/t-j-fryer/iProteinStudio` (renamed from NanoHunterStudio) |
| **Runtime** | `~/.iproteinstudio` — **not** Application Support: a space in the path breaks every Python console-script shebang |

**Working:** setup wizard with per-engine choice, worked examples (α-cobratoxin
with its alignment included, and fluorescein), workspace management, a
prediction-only tab that reuses every alignment on the machine, nanobody/mini-binder/peptide design form,
live metrics dashboard, hits gallery, offline py2Dmol structure viewer with visual controls, target prep,
predictions library, a unified in-app structure/metric browser for completed
Predict, iterative and RFdiffusion3 runs, persistent per-workspace run history and
a global Activity panel with exact checkpoint Resume for newly recorded iterative campaigns.
Protein multimers now report conservative PAE-derived ipSAE(min) from Boltz,
IntelliFold or Protenix in saved outputs and the GUI; OpenFold is excluded because
its current output is PDE rather than PAE.
Protenix masked-residue handoffs are chain-aware and chemically normalized before
inverse folding: its generic `CG` pseudo-atom is removed before `UNK` becomes
alanine, while backbone coordinates are preserved exactly.
Protein sequence fields share one colon-separated multimer syntax and display the
resolved chain map. Predict uses A/B/C input order; binder-design workflows reserve
A and keep targets as B/C/D, with distinct query-validated MSAs per target subunit.
RFdiffusion3 normalizes selected external PDB/mmCIF chains into that convention.

**Also working:** Ligand Intelligence — chemistry QA, recognition-core vs linker
separation, conformer ensembles weighed against experimental PDB structures, and a
design budget split across the shapes a molecule actually adopts, with directed
core-to-linker bonds, annotated RFD atom names, reviewed condition suggestions and
stereochemistry-safe PDB evidence; choice of design predictor (Boltz-2 ± potentials,
experimental Protenix Constraint v0.5 pocket proposals, Protenix v2/Mini, or
IntelliFold PyTorch v2-flash/full v2)
with IntelliFold or OpenFold-3 orthogonal checking; measured-optimum scheduling
delegated to NanoHunter's runner; a pinned standalone installation that does not
need a sibling checkout, with explicit reuse of an existing NanoHunter/RFD3
install as an option; an RFdiffusion3 tab that drives the
validated production pipeline, survives quitting the app, resumes protein stages
and small-molecule stages from checkpoints and presents its ranked-result summary.
Protenix uses native MPS with no CPU fallback, owns its upstream public MSA-server
route, preserves explicit single-sequence requests without contacting that route,
and is a removable managed component rather than a hidden Boltz dependency.
IntelliFold runs through a pinned native-MPS launcher that rejects Accelerate CPU
fallback and incomplete seed/sample output sets. Managed engines retain separate
dependency contracts while sharing APFS-cloned package payloads, Git objects and
one checksum-verified Protenix chemical dataset; the Engines screen can safely
consolidate matching assets from an older install.

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
5. No app icon. Sparkle self-update, size-aware engine consent and release automation are implemented, but Developer ID signing/notarisation and an old-to-new update acceptance on a second Mac remain blocked on Apple distribution credentials.

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
| 0051 | 2026-08-31 | [Minimize managed runtime storage without merging incompatible engines](lab_book/0051-minimize-managed-runtime-storage.md) | Nine scientifically incompatible runtime boundaries remain isolated while APFS-cloned packages, shared Git objects and verified Protenix data reduce safe physical duplication; cold install, receipt and post-cache-clean inference pass |
| 0050 | 2026-08-31 | [Enforce iterative cardinality and complete installer v2](lab_book/0050-enforce-cardinality-and-complete-installer-v2.md) | GUI counts are preserved and audited with cycle 00 separate, live result inspectors have a stable closeable owner, and the deterministic versioned installer passes a real isolated cold MPNN install plus inference |
| 0049 | 2026-08-31 | [Promote resident scheduling and installer hardening](lab_book/0049-promote-resident-scheduling-and-installer-hardening.md) | Integrated release policy, deterministic command/download/cancellation/result contracts, full Swift build and packaged-app verification for the two independently developed branches |
| 0048 | 2026-08-31 | [Harden managed installation without perturbing the resident benchmark](lab_book/0048-harden-managed-runtime-installer.md) | Install locking, sleep protection, durable logs, disk preflight, descendant cancellation, explicit partial/broken states, verified resumable downloads and transactional resource staging pass synthetic contracts and the full Swift build |
| 0047 | 2026-08-31 | [Audit and simplify the managed runtime installer](lab_book/0047-audit-managed-runtime-installer.md) | Why the nine logical environments should remain isolated, where the current install is not truly self-contained, and the ordered transactional/locked/shared-storage architecture that should replace in-place setup |
| 0046 | 2026-08-30 | [Implement campaign-resident iterative predictors](lab_book/0046-implement-campaign-resident-predictors.md) | The complete 18-arm SUMO campaign produced 1,080/1,080 designs; measured optimized defaults are resident workers for five engines and cycle-wave for full Protenix v2 |
| 0045 | 2026-08-30 | [Validate cycle waves before promoting model residency](lab_book/0045-validate-cycle-waves-before-residency.md) | Directory replay is not live persistence; Protenix cycle-wave execution, explicit predictor work controls, resume timing provenance and governed SUMO/helix validation are added while resident defaults remain gated |
| 0044 | 2026-08-27 | [Separate signed app updates from explicit checkpoint downloads](lab_book/0044-signed-app-updates-and-engine-consent.md) | Pinned Sparkle integration, versioned bundles, visible release notes/settings, duplicate-copy cleanup, final engine-download consent and fail-closed signing/notarisation automation; existing pre-updater copies still need one manual signed upgrade |
| 0043 | 2026-08-27 | [Recover the full Protenix Constraint macOS validation record](lab_book/0043-protenix-constraint-macos-validation-lineage.md) | Raw beta logs, receipts, paired outputs, memory/timing data, figures and ChimeraX artifacts establish exactly what was required to run the v0.5 checkpoint on native MPS and what its pocket/contact results do—and do not—show |
| 0042 | 2026-08-27 | [Complete the Protenix Constraint install and documentation contract](lab_book/0042-complete-protenix-constraint-install-contract.md) | Fresh install, reuse, materialisation, removal, bundle staging and CLI/UI documentation now agree on one isolated experimental design-only checkpoint with verified weights and no CPU fallback |
| 0041 | 2026-08-27 | [Exclude the unoptimized seed from iterative re-checks](lab_book/0041-exclude-cycle00-from-post-checks.md) | “All design cycles” now means optimized cycles 01 through N in the UI, command contract and runtime estimate; cycle 00 remains an explicit CLI-only diagnostic opt-in |
| 0040 | 2026-08-27 | [Add Protenix Constraint v0.5 as an honest experimental pocket engine](lab_book/0040-protenix-constraint-pocket-engine.md) | Isolated ESM-free native-MPS install, exact pocket handoff and result geometry; one installed 10×200 acceptance reproduced the prior weak alternative-pocket response rather than overstating it |
| 0039 | 2026-08-26 | [Make iterative resume, score provenance and partial results explicit](lab_book/0039-resume-provenance-and-persistent-results.md) | Explicit Resume semantics, measured checkpoint reuse, browseable interrupted outputs, per-score engine/stage provenance, non-Boltz full-target design and Target Prep layout |
| 0038 | 2026-08-25 | [Unify multichain input and backend routing](lab_book/0038-unify-multichain-input.md) | Colon syntax, visible chain assignment, reserved binder-chain conventions, per-subunit MSAs, chain-qualified hotspots and RFdiffusion3 PDB/mmCIF normalization |
| 0037 | 2026-08-25 | [Normalize Protenix unknown-residue handoffs](lab_book/0037-normalize-protenix-unk-handoffs.md) | Why Protenix `UNK` cannot be renamed textually, the chain-scoped alanine repair, and why backbone-only SolubleMPNN campaigns do not require restarting |
| 0036 | 2026-08-23 | [Add conservative ipSAE(min) scoring from real PAE outputs](lab_book/0036-add-conservative-ipsae-scoring.md) | The exact directional-minimum definition, PAE-capable engine routes, Protenix full-confidence requirement, fail-loud exclusions and unchanged design rank policy |
| 0035 | 2026-08-22 | [Make MSA and accelerator policy fail-loud](lab_book/0035-fail-loud-msa-and-mps-policy.md) | Why Protenix treated explicit-empty MSAs as search permission, how mixed-chain policy is preserved, and how every IntelliFold route now rejects CPU fallback and incomplete outputs |
| 0034 | 2026-08-22 | [Organize the app around workspaces and a first-class library](lab_book/0034-workspaces-and-library.md) | Why the old Design Projects framing was obsolete, how prediction-first work starts without a fake design campaign, safe migration, unique output paths, and discoverable renaming |
| 0033 | 2026-08-21 | [Audit the rebuilt app and preserve explicit MSA policy](lab_book/0033-end-to-end-application-audit.md) | Current GUI/runtime acceptance, the explicit single-sequence OpenFold bug, one shared query builder, and bounded GPU coverage of every supported predictor/model variant |
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
