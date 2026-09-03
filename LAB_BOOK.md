# Lab Book

The project's memory. Every experiment, decision, benchmark and non-obvious bug that
shaped this repository is recorded here — including the ones that did not work.

**If you are an AI agent picking up this repository: read [`CLAUDE.md`](CLAUDE.md), then
this file, then any entry it points you at. Recording your own work here is mandatory.**

---

## Current status

_Last updated: 2026-09-02_

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
with IntelliFold or OpenFold-3 orthogonal checking; automatic measured-optimum
scheduling that keeps five design engines resident and uses cycle waves for full
Protenix v2; a pinned standalone installation that does not
need a sibling checkout, with explicit reuse of an existing NanoHunter/RFD3
install as an option; an RFdiffusion3 tab that drives the
validated production pipeline, survives quitting the app, resumes protein stages
and small-molecule stages from checkpoints, and presents generated backbones,
verification structures, score distributions and hit verdicts while they arrive.
Partial diffusion and motif scaffolding include runnable p53–MDM2 examples;
motif provenance follows exact functional atoms from source residues through
generated positions, sequence design and independent-prediction recovery.
Codex and Claude can use the same local least-privilege MCP bridge to inspect
managed projects, freeze reproducible plans and run resumable workflows without
an arbitrary shell; immutable runner provenance and one shared agent execution
lock protect cross-client campaigns (Entry 0069).
The app now installs or removes Codex and Claude Desktop access with explicit
buttons, and an opt-in capability-authenticated loopback gateway provides the
local half of ChatGPT/phone delegation without silently publishing the Mac
(Entry 0070).
Protenix uses native MPS with no CPU fallback, owns its upstream public MSA-server
route, preserves explicit single-sequence requests without contacting that route,
and is a removable managed component rather than a hidden Boltz dependency.
IntelliFold runs through a pinned native-MPS launcher that rejects Accelerate CPU
fallback and incomplete seed/sample output sets. Managed engines retain separate
dependency contracts while sharing APFS-cloned package payloads, Git objects and
one checksum-verified Protenix chemical dataset; the Engines screen can safely
consolidate matching assets from an older install.
New runs retain dense Protenix/IntelliFold confidence data as checksum-verified
gzip, keep one canonical copy of selected structures and batch logs, and share
exact A3Ms plus independently resumable pipeline snapshots through a
content-addressed APFS store (Entry 0064).

Build 10's post-macOS-update M1 Pro acceptance produced valid Boltz and IntelliFold
structures with both compatibility boundaries active. IntelliFold was nevertheless
reported as failed because the post-run validator excluded its upstream
`_inputs/predictions` output path. Build 11 fixes that bookkeeping defect without
admitting arbitrary staged coordinate inputs (Entry 0065).

Controlled unsigned-beta packaging now produces versioned Apple-Silicon DMG and
ZIP artifacts with checksums, provenance, embedded notices and a trusted Sparkle
update boundary. Beta archives require the project's EdDSA signature even though
the application remains ad-hoc signed and unnotarised by Apple. The notarised
release route remains intact, and privacy, support, security and the unresolved
MIT licensing review are documented explicitly.

The first external build exposed and build 3 fixes a clean-Mac startup crash in
SwiftPM's executable-resource accessor. Packaged resources now use the sealed
`Contents/Resources` location through an app-aware resolver, and the shipped
binary contains no absolute checkout path. Release validation launches the app
outside the source checkout before handoff.

**Known gaps, in priority order:**

1. Exact-manifest Resume is implemented, but still needs a deliberate
   interrupt/relaunch/resume acceptance run from GUI controls. Complete RFD3 and
   nanobody routes were exercised through their production entry points rather
   than a heavy GUI click — see [0016](lab_book/0016-complete-campaigns-and-run-recovery.md).
2. Accessibility labels now cover examples, primary Start actions, navigation
   and the active-run banner, but the remaining forms have not had a complete
   VoiceOver, keyboard-focus, large-text or contrast pass.
3. The new RFdiffusion3 partial/motif examples have single-backbone 200-step MLX
   acceptance, exact motif-atom recovery and an MPNN handoff test. Their complete
   multi-predictor campaigns and experimental enrichment are not yet calibrated.
4. OpenFold-3 complex pLDDT has an unresolved scale problem — see
   [0002](lab_book/0002-inherited-speed-lessons.md) §7.
5. No app icon. Sparkle self-update, size-aware engine consent, signed-release automation and a trusted unsigned-beta route are implemented, but Developer ID signing/notarisation and an old-to-new update acceptance on a second Mac remain blocked on Apple distribution credentials. The unsigned path still needs its first second-Mac Gatekeeper/install test and a real beta-to-beta Sparkle acceptance test.

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
| 0070 | 2026-09-02 | [Add one-click AI clients and a private remote gateway](lab_book/0070-add-one-click-ai-and-private-remote-gateway.md) | Moves Codex and Claude Desktop registration into explicit UI controls and adds a read/run-only authenticated loopback transport for remote clients while keeping public HTTPS exposure a separate user choice. |
| 0069 | 2026-09-02 | [Add a client-neutral agent bridge](lab_book/0069-add-client-neutral-agent-bridge.md) | Gives Codex and Claude the same least-privilege MCP profiles, immutable plan/start contract, durable serialized workers, bounded results and non-destructive client configuration without exposing an arbitrary shell. |
| 0068 | 2026-09-02 | [Reuse resident predictors for RFdiffusion3 validation](lab_book/0068-reuse-resident-predictors-for-rfd3-validation.md) | Applies the measured iterative-design scheduling policy to RFdiffusion3 complex and binder-only verification, with one resident MPS model per stage and the faster cycle-wave exception for full Protenix v2. |
| 0067 | 2026-09-02 | [Add live RFdiffusion3 results and exact motif recovery](lab_book/0067-add-live-rfd3-results-and-exact-motif-recovery.md) | Makes accepted structures and score distributions visible during campaigns, adds runnable p53–MDM2 examples, repairs explicit side-chain atom conditioning in the MLX adapter, and validates source-to-design motif correspondence at the default diffusion schedule. |
| 0066 | 2026-09-02 | [Add RFdiffusion3 partial diffusion, motif scaffolding and dual validation](lab_book/0066-add-rfd3-partial-motif-and-dual-validation.md) | Separates de-novo, partial and motif workflows; ports current partial scheduling to MLX; rejects malformed motif outputs; and makes target-aligned pose, binder-fold and binder-alone validation auditable in persistent results. |
| 0065 | 2026-09-02 | [Accept IntelliFold outputs below its staged input directory](lab_book/0065-accept-intellifold-staged-output-layout.md) | M1 build-10 inference succeeded but a broad `_inputs` filter rejected the valid result; discovery now accepts only `_inputs/predictions` and regression coverage reproduces Plain Predict's exact layout. |
| 0064 | 2026-09-02 | [Make run storage lossless and deduplicated](lab_book/0064-make-run-storage-lossless-and-deduplicated.md) | Dense confidence output is checksum-compressed, aliases/logs stop copying canonical bytes, A3Ms and exact pipeline snapshots share content-addressed APFS storage, and real MPS smoke outputs pass geometry. |
| 0063 | 2026-09-01 | [Test runtime consolidation without touching the trusted install](lab_book/0063-test-runtime-consolidation-safely.md) | Isolated final-RC PyTorch 2.14 preserves an M4 Boltz fold and removes its observed SVD fallback; one shared Protenix dependency base is feasible, while production promotion remains gated on stable-wheel, M1 and full installer/model regression. |
| 0062 | 2026-09-01 | [Audit the Boltz MPS reset across Apple GPU generations](lab_book/0062-audit-boltz-mps-cross-generation.md) | Shows that the 4-second number was model-only, proves the build-9 reset leaves a paired M4 fold bit-identical with no detected timing penalty, and anchors the M1/M4 divergence in PyTorch and Apple primary evidence. |
| 0061 | 2026-09-01 | [Finish the M1 predictor-correctness repair](lab_book/0061-finish-m1-predictor-correctness.md) | Records the decisive build-8 M1 failures, replaces all three IntelliFold GatherND formulations, adds the PyTorch-MPS allocator boundary to Boltz and defines the remaining M1 acceptance gate. |
| 0060 | 2026-09-01 | [Make Boltz and IntelliFold Apple-GPU output fail-safe](lab_book/0060-fix-boltz-intellifold-apple-gpu-correctness.md) | Adds the geometry gate and records the initial FP32/single-GatherND repair; its Boltz root-cause claim and incomplete IntelliFold patch are explicitly superseded by Entry 0061. |
| 0059 | 2026-09-01 | [Make prediction MSA failures retryable and diagnosable](lab_book/0059-make-prediction-msa-failures-diagnosable.md) | Confirms both public MSA routes are live, adds bounded retries to plain Predict, and preserves the actual provider/network cause and full log without allowing a silent single-sequence fallback. |
| 0058 | 2026-09-01 | [Close the remaining clean-Mac installer failures](lab_book/0058-close-clean-mac-installer-failures.md) | Uses six external install logs to repair Protenix nounset initialization, LASErMPNN's incorrect filelock hashes and pip-less RFdiffusion3 receipts, while making the mandatory four-model MPNN core suite explicit in Engines. |
| 0057 | 2026-09-01 | [Repair the fresh AntiFold hash-locked install](lab_book/0057-repair-antifold-hash-lock.md) | Reproduces the external installer failure, removes an unnecessary `wheel` entry with an unhashed transitive dependency, and validates the exact transactional install plus a real one-sequence AntiFold MPS run. |
| 0056 | 2026-09-01 | [Fix the clean-Mac packaged-resource startup crash](lab_book/0056-fix-clean-mac-resource-crash.md) | Diagnoses the external build 2 `Bundle.module` crash, removes SwiftPM's absolute build-machine fallback from shipped code, packages resources conventionally, and validates build 3 from the mounted DMG outside the checkout. |
| 0055 | 2026-09-01 | [Enable cryptographically verified Sparkle updates for trusted betas](lab_book/0055-enable-sparkle-for-trusted-betas.md) | Enables EdDSA-verified application updates in ad-hoc trusted betas, preserves the Apple trust warning, and adds an atomic clean-tree GitHub prerelease/appcast publishing route. |
| 0054 | 2026-09-01 | [Package auditable unsigned betas without weakening signed releases](lab_book/0054-package-auditable-unsigned-betas.md) | Adds versioned unsigned DMG/ZIP packaging, checksums, provenance and distribution notices; its original manual-update decision is superseded by Entry 0055's trusted-beta channel. |
| 0053 | 2026-09-01 | [Make measured resident scheduling automatic](lab_book/0053-make-resident-scheduling-automatic.md) | Removes scheduling as a GUI preference, migrates old Compatibility forms, and enforces resident workers for five engines with the measured cycle-wave exception for full Protenix v2 |
| 0052 | 2026-08-31 | [Audit and archive the pre-standalone runtime](lab_book/0052-audit-and-archive-legacy-runtime.md) | Removes the verified redundant Boltz archive and preserves historical projects, RFdiffusion3 artifacts and licensed AF3 parameters before the separately approved deletion of the obsolete 23 GB runtime |
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
