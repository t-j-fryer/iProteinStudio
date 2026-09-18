# Lab Book

The project's memory. Every experiment, decision, benchmark and non-obvious bug that
shaped this repository is recorded here — including the ones that did not work.

**If you are an AI agent picking up this repository: read [`CLAUDE.md`](CLAUDE.md), then
this file, then any entry it points you at. Recording your own work here is mandatory.**

---

## Current status

_Last updated: 2026-09-17_

| | |
|---|---|
| **Stage** | Alpha. Debug and release builds pass; a standalone managed install has completed acceptance folds. Signed-update code and release automation are implemented, but no Developer ID certificate is installed and no notarised public build has shipped. |
| **Platform** | macOS 14+, Apple Silicon only. Developed on M4 Max / 64 GB / macOS 26.x. |
| **Repo** | Public — `github.com/t-j-fryer/iProteinStudio` (renamed from NanoHunterStudio) |
| **Runtime** | `~/.iproteinstudio` — **not** Application Support: a space in the path breaks every Python console-script shebang |

**Installer:** Build 34 adds a checksum-verified AbMPNN fallback and continues independent components after installation failures. Partial setup reports unfinished components for retry; completed engines remain available (Entry 0124).

**Resume:** Build 35 adds verified per-prediction checkpoints to resident IntelliFold Full/Flash and live completed/reused counts. Software interruption fixtures pass; existing campaigns retain their older frozen runtime (Entry 0127).

**Queue:** Build 36 allows queued submissions from Protein Hunter, NISE,
RFdiffusion3 and Predict across workspaces, with a global queue popover and
observation-only New run navigation. Inert mixed-workflow serialization and
startup cancellation fixtures pass (Entry 0129).

**Atom controls and names:** Build 37 fixes lost atom-selector edits and hidden
molecule highlights, and adds optional names beside Start/Add to Queue in all
four tabs (Entry 0130).

**RFdiffusion3 audit:** Source fixes cover optional atom selections, verified
resume and output qualification. Software regression tests and the app build pass;
new real-model smoke testing and deployment remain outstanding (Entry 0132).

**OpenFold queue fix:** The app now uses OpenFold-3's supported per-trajectory
scheduler and rejects unsupported residency during batch preflight. The three
affected Bgx batches have 4,500 completed optimized structures and 750 outstanding;
the ten unfinished OpenFold campaigns have now been submitted as corrected
immutable jobs (one running and nine queued at restart). Rebuilt local app;
historic failed plans and completed results are preserved (Entries 0133, 0136).

**Working:** NISE now offers Protein Hunter hallucination or experimental
RFdiffusion3 initial backbones (Entry 0103), now with 1,000 starts by default
(Entry 0135).
NESSO installs its required ESM-2 650M assets automatically and can reuse exact
verified cache files. NISE separates initial backbone generation from optimisation,
with typed budgets, explicit sequences-to-advance and optional experimental
NESSO sequence screening before Boltz (Entry 0102). Its worker and screening contracts have fixture coverage. The resident 50-design
fluorescein benchmark (Entry 0118) found NESSO 6.16× faster but weak Boltz rank
agreement; full NISE screening-campaign acceptance remains pending.

**NISE search policy:** New requests use 1,000 starts, 30 maximum cycles,
four-cycle patience and beam three. Sampling is 64 proposals from the starting
seed, then 32 per parent (up to 96 per trajectory). Adaptive stays off. Optional
ligand-local X-token masking adds a separately scored/repaired branch from cycle
2 and replaces one ordinary sampling parent and advancement place, using an
experimental 6 Å / 25% starting setting (64 ordinary + 32 masked + 32 repair
predictions per later trajectory-cycle). Software route/replay checks pass;
a five-start biotin pilot stopped at first-refinement exposure/score filters,
so guarded continuation holds the large campaign. Build 38 / MCP 19 are deployed
and published on GitHub; all six XCTest cases now pass after Xcode setup
(Entries 0137, 0140, 0143, 0144).

Setup wizard with per-engine choice, worked examples (α-cobratoxin
with its alignment included, and fluorescein), workspace management, a
prediction-only tab that reuses every alignment on the machine, nanobody/mini-binder/peptide design form,
live metrics dashboard, hits gallery, offline py2Dmol structure viewer with visual controls, target prep,
predictions library, a unified in-app structure/metric browser for completed
Predict, iterative and RFdiffusion3 runs in movable, resizable result windows,
persistent hierarchical result groups: RFdiffusion3 backbones contain their
MPNN derivatives and iterative runs contain their cycles; every child keeps its
design/complex/binder-alone structures and scores together. Compact cards use
control-free previews and one spacious selected py2Dmol viewer (Entry 0082).
Iterative run viewers additionally offer a target-fitted cycle trajectory with
labelled scrubbing, autoplay and playback-speed controls (Entry 0083).
The shipped client-neutral MCP bridge is now v10 (including NISE/NESSO): its read/run profiles expose
the same run→cycle and backbone→MPNN-derivative result hierarchy through
`results_overview`, keep hit verdicts on checked children, and instruct every
client to use outward whole-surface ORI coverage when a protein epitope is
omitted (Entry 0084).
Iterative de-novo design now offers explicit natural, anti-helix, β-oriented,
and mixed sequence priors. β-oriented trajectories save a deterministic
strand/turn plan and can apply it either to cycle 00 only or to cycle 00 plus
every MPNN redesign, enabling matched-scope experiments. The controls remain
labelled experimental until predicted-coordinate validation is completed
(Entry 0085).
Unconditioned monomers can now opt into bounded initialization refinement through
the shared CLI/MCP runner. Separate assessment, regional resampling and scheduler
handoff preserve originals and explicit exhaustion, with synthetic lifecycle and
integration coverage. This path currently uses the per-run scheduler and has no
new GUI controls or measured real-model effectiveness (Entry 0095).
A paired 90-residue Boltz-2 monomer screen now covers 22 declared control
conditions with ten trajectories of five cycles each and β-only inspection.
The 22-condition monomer screen is complete: 214/220 trajectories completed
five cycles, with five budget exhaustions and one geometry rejection retained.
Full output inspection reproduces coordinate assignments and initialization
decisions. Proline suppression strongly favors helices; no sheet-enrichment
advantage over baseline is resolved by the paired intervals. No control is
promoted (Entry 0100).
One saved multi-filter hit definition is shared by Browse Results and live Hits,
persistent per-workspace run history and
a global Activity panel with exact checkpoint Resume for newly recorded iterative campaigns.
Iterative protein design can optionally guide target chains from a checksummed
PDB/CIF with Boltz, full Protenix v2, or IntelliFold v2 Flash/full; stronger
Boltz coordinate restraint is disabled after reproducible Apple-GPU geometry
failures, while binder and independent validation folds stay untemplated.
Protenix template support includes a pinned managed Kalign build (Entry 0080).
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
Its live and completed result browser retains generated MLX backbones alongside
complex and binder-alone predictions, with the emitting engine identified.
The bundled alpha-cobratoxin example now uses complete experimental RCSB 1CTX
coordinates, and the MLX exporter retains all residue-specific target atoms
instead of dropping atom14 side-chain slots before name conversion (Entry 0078).
Protein de-novo campaigns now use explicit whole-surface, broad-region,
targeted-epitope, or advanced manual-XYZ placement. An unspecified site maps to
reproducible solvent-surface coverage, never the fixed protein centre of mass;
broad-region residues are positioning anchors rather than hidden hotspots
(Entry 0077).

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
The run profile now includes its own read/result tools, and MCP result queries
surface generated MLX backbones, complex predictions, binder-alone predictions
and their engine/context provenance, including bounded compatibility labels for
older Studio runs (Entry 0075).
The bridge now serves universal workflow guidance, derives protein de-novo
contigs inside the pinned MLX adapter boundary, enforces protein/small-molecule
model routing and returns the real pipeline and RFdiffusion3 stage errors instead
of inviting agents to guess or request arbitrary folder access (Entry 0071).
The cross-modal executable audit in Entry 0073 additionally makes ligand
campaign startup same-file-safe, stores Foundry fixtures with each campaign,
and separates same-length conformer queues while preserving exact design quotas.
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

The source findings from [0087](lab_book/0087-review-repository-product-reliability.md)
are addressed by the implementation in
[0088](lab_book/0088-implement-product-reliability.md): recoverable workspace
saving/archive, shared durable native/MCP jobs, saved dashboard context,
accessibility controls, asynchronous result loading and an explicit test runner.
The app builds and fixture suites pass apart from the unavailable XCTest module
in this Command Line Tools installation. Full GUI/VoiceOver, crash/relaunch and
release acceptance remain outstanding; the implementation is not a certification
of those behaviours.

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

**Deliberately out of scope:** protein/cross-reactive NISE; RFdiffusion3
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
| 0151 | 2026-09-17 | [Single-particle guidance and early exposure](lab_book/0151-biotin-single-particle-and-early-exposure.md) | Complete: 30-input physical/FK-off replay and 1,230 exposure snapshots; early rejection loses passers, late persistence remains exploratory. |
| 0150 | 2026-09-17 | [Biotin guidance/request replay](lab_book/0150-biotin-guidance-replay.md) | 30 paired starts:48.69→15.48→14.43s; pocket-only causes11 wrong-chirality ligands. Batching saves6.82%; main run paused. |
| 0149 | 2026-09-17 | [Explain biotin Boltz timing](lab_book/0149-explain-biotin-boltz-timing.md) | Historical potentials-off worker predictions average20–21 s; current guided biotin initialization52 s. Three internal steering particles; residency intact and no initial affinity head. |
| 0148 | 2026-09-17 | [Launch biotin without partial noising](lab_book/0148-launch-biotin-without-partial-noising.md) | Approved 1000-start request submitted; job-002ee4e5c61e running with a resident MPS worker and noising disabled |
| 0147 | 2026-09-17 | [Biotin settings without partial noising](lab_book/0147-biotin-settings-without-partial-noising.md) | Revised draft disables noising and uses three ordinary parents:64 first-cycle proposals,96 later;47,784 total structure-prediction ceiling. Launched in0148. |
| 0146 | 2026-09-17 | [Review partial-noising beam semantics](lab_book/0146-review-partial-noising-beam-semantics.md) | Third-ranked repair has no descendants; effective search is two active parents plus a noising proposal route. Policy clarification recommended, not implemented. |
| 0145 | 2026-09-17 | [Test noising from a previous biotin parent](lab_book/0145-test-noising-from-previous-biotin-parent.md) | Real branch passes: five folds, four affinity evaluations, one resident worker; repaired winner scores below parent and ligand-pose movement remains significant |
| 0144 | 2026-09-17 | [Complete XCTest validation](lab_book/0144-validate-xcode-tests.md) | All six XCTest tests and app build pass after Xcode setup; biotin pilot attrition diagnosed and full campaign remains held |
| 0143 | 2026-09-17 | [Start biotin acceptance and update Studio](lab_book/0143-biotin-launch-and-update.md) | Build 38 / MCP 19 and GitHub release deployed; guarded biotin continuation subsequently stopped on pilot attrition (0144) |
| 0142 | 2026-09-17 | [Limit biotin exposure to terminal oxygens](lab_book/0142-limit-biotin-exposure-to-terminal-oxygens.md) | Revised draft exposes only O18/O19 at 50%; removes carbon exposure constraints, preserves all other settings and 55,208 prediction ceiling |
| 0141 | 2026-09-17 | [Compare NISE exposure methods](lab_book/0141-compare-nise-exposure-methods.md) | Studio uses per-atom retained SASA throughout; reported Cα alpha-hull/five-ray method is not equivalent and its exact code remains unavailable |
| 0140 | 2026-09-17 | [Replace an ordinary sampling parent with noising](lab_book/0140-correct-noising-parent-budget.md) | Two ordinary parents plus one noising branch; 128 later folds per trajectory, revised biotin maximum 55,208; free-ligand terminal exposure retained |
| 0139 | 2026-09-17 | [Review biotin attachment atoms and noising scale](lab_book/0139-review-biotin-noising-plan.md) | Prior atom map verified; free-acid versus conjugated-amide distinction; draft 62,632-fold upper bound, attachment confirmation and pilot pending |
| 0138 | 2026-09-17 | [Plot completed Bgx minibinder and nanobody overviews](lab_book/0138-plot-completed-bgx-overviews.md) | Reference-style figures from 5,250 audited structures; scaffold-specific nanobody confidence and pooled per-engine timing; SVG/PDF/PNG exports |
| 0137 | 2026-09-16 | [Separate NISE budgets and add optional ligand-local masking](lab_book/0137-nise-fixed-budgets-and-partial-noising.md) | First cycle 64, later 32 per parent with beam three; experimental masked-backbone/MPNN repair branch reserves one place, remains off, with route/replay fixtures passing |
| 0136 | 2026-09-16 | [Restart outstanding OpenFold campaigns](lab_book/0136-restart-outstanding-openfold-runs.md) | Ten corrected immutable plans submitted; one running and nine queued for 750 optimized designs, retaining original inputs, seeds and snapshots |
| 0135 | 2026-09-16 | [Audit fluorescein score progression before choosing adaptive sampling](lab_book/0135-fluorescein-nise-adaptive-retrospective.md) | Requested 1,000/30/4 defaults; 5,440-fold audit finds rare cycle winners and small late gains; adaptive policy remains unpromoted |
| 0134 | 2026-09-16 | [Add the NISE efficient search policy](lab_book/0134-nise-efficient-search-policy.md) | Shared early gate, geometry-first selective affinity, eight-cycle default and optional resumable adaptive top-ups without rollback/rescue |
| 0133 | 2026-09-16 | [Fix OpenFold scheduling and audit stalled batches](lab_book/0133-fix-openfold-scheduler-and-audit-queue.md) | Supported OpenFold scheduling, early batch rejection, 4,500 verified optimized structures and 750 outstanding; local app rebuilt and original jobs left paused |
| 0132 | 2026-09-16 | [Audit and harden the RFdiffusion3 pipeline](lab_book/0132-audit-and-harden-rfd3-pipeline.md) | Empty selections, verified resume, disjoint queue seeds, exact designer routing, finite ranking and complete multi-engine hit checks |
| 0131 | 2026-09-16 | [Audit three test2 NISE campaigns](lab_book/0131-audit-test2-nise-runs.md) | Stage attrition, historical-winner caveat, NESSO gate exhaustion and RFD3 empty buried-atom metrics crash |
| 0130 | 2026-09-09 | [Fix atom controls and name runs](lab_book/0130-atom-controls-and-run-names.md) | Native Bind/Expose click regression; visible highlights; atomic contact/linker updates; saved names across all tabs |
| 0129 | 2026-09-09 | [Queue all Studio workflows](lab_book/0129-queue-all-studio-workflows.md) | All four tabs accept waiting work; global queue controls; independent saved runs and startup cancellation handling |
| 0118 | 2026-09-09 | [Compare resident NESSO and Boltz2](lab_book/0118-resident-nesso-boltz-fluorescein.md) | 50 paired designs: NESSO 6.16× faster, weak Boltz rank agreement (ρ = 0.106); original design batch resumed. |
| 0119 | 2026-09-09 | [Add nanobody scaffold selection and budgets](lab_book/0119-nanobody-scaffold-budgets.md) | Equal/custom per-scaffold allocations across engines; add tail-trimmed 3EAK with explicit CDR provenance. |
| 0120 | 2026-09-09 | [Sync accumulated Studio changes to GitHub](lab_book/0120-sync-studio-to-github.md) | Publish the coherent build-32 source tree, tests and validation harnesses; generated artifacts stay separate. |
| 0121 | 2026-09-09 | [Guide Apple tools installation in the app](lab_book/0121-guide-apple-tools-installation.md) | Native Apple installer and Software Update actions; preserve reviewed setup choices and recheck the compiler on retry. |
| 0128 | 2026-09-09 | [Stop IntelliFold and relaunch build 35](lab_book/0128-stop-intellifold-and-relaunch-build35.md) | Cycle 01 already complete; broker cancellation preserves 50 results; updated app reopened, campaign remains stopped |
| 0127 | 2026-09-09 | [Checkpoint resident IntelliFold predictions](lab_book/0127-checkpoint-resident-intellifold-predictions.md) | Per-item verified resume and live progress; hard-interruption fixtures; existing frozen runs remain unchanged |
| 0126 | 2026-09-09 | [Inspect live IntelliFold cycle 01 progress](lab_book/0126-inspect-live-intellifold-cycle01-progress.md) | Active resident worker; 48/50 predictions at 4.2 min each; resumed unfinished batch repeated 34 completed predictions |
| 0125 | 2026-09-09 | [Confirm the completed AbMPNN timeout log](lab_book/0125-confirm-completed-abmpnn-timeout-log.md) | Longer copy of the earlier attempt confirms 20 zero-byte AbMPNN retries and a final read timeout; build 34 was not exercised |
| 0124 | 2026-09-09 | [Isolate installation failures and add the verified AbMPNN fallback](lab_book/0124-isolate-install-failures-and-add-abmpnn-fallback.md) | Pinned equivalent checkpoint, component-level continuation, partial result and narrow retry; build 34 |
| 0123 | 2026-09-09 | [Check Zenodo status and verify an AbMPNN alternative](lab_book/0123-check-zenodo-status-and-abmpnn-alternative.md) | Wider access failures; Mosaic's re-serialized checkpoint has 472 exactly matching tensors and metadata, with a distinct pinned file checksum. |
| 0122 | 2026-09-09 | [Investigate AbMPNN download connectivity](lab_book/0122-investigate-abmpnn-download.md) | Supplied log retries from 0 B; independent Zenodo checks return a gateway timeout or stall. Existing verified downloads are retained. |
| 0117 | 2026-09-09 | [Estimate active IntelliFold Full run](lab_book/0117-estimate-active-intellifold-full-run.md) | Current 50 × 5 campaign: about 17 hours left for Full at observed pace; OpenFold3 follows. |
| 0116 | 2026-09-09 | [Add overview design timing](lab_book/0116-add-overview-design-timing.md) | Both completed overviews show audited elapsed seconds per optimized design, with overlapping resident timers counted once. |
| 0115 | 2026-09-09 | [Share cropped-interface NESSO screening](lab_book/0115-share-cropped-nesso-screening.md) | Corrects entropy to entropy_crop_pl; optional post-campaign Protein Hunter and pre-fold RFD3 top-X verification with shared resident workers and audited resume. |
| 0114 | 2026-09-09 | [Rank NESSO by binding and placement confidence](lab_book/0114-nesso-placement-confidence-ranking.md) | Both screens use P(bind) + (1 − entropy_pl); invalid/near-zero placements are excluded and the policy/components are audited. |
| 0113 | 2026-09-09 | [Add initial NESSO screening and clear run metadata](lab_book/0113-initial-nesso-screening-and-run-metadata.md) | Independent initial/optimisation screens, original-lineage caps and advanced stage controls; applicable run settings separated from inactive restoration state. |
| 0112 | 2026-09-08 | [Audit inactive settings in a minibinder manifest](lab_book/0112-audit-minibinder-inactive-settings.md) | Confirms all 50 trajectories and 250 MPNN logs used full-chain minibinder design; scaffold/CDR and beta fields were inactive saved state. |
| 0111 | 2026-09-08 | [Verify NISE atom identity and add linker exposure requirements](lab_book/0111-nise-atom-identity-and-linker-exposure.md) | Shared chemical state, exact Boltz mapping, separate NESSO names, RFdiffusion3 conditioning/translation and audited contact/SASA gates; real-model efficacy pending. |
| 0110 | 2026-09-08 | [Fix workspace clicks and Apple compiler setup](lab_book/0110-workspace-clicks-and-apple-compiler-setup.md) | Explicit single-click switching and workspace-bound edits; configures SDK/C++ headers before downloads, reproduces ProDy build locally, M1 retry pending. |
| 0109 | 2026-09-08 | [Expose OpenFold-3 and explicit IntelliFold design checkpoints](lab_book/0109-explicit-protein-hunter-checkpoints.md) | Adds independent Flash/Full design selections and OpenFold-3, explicit checkpoint routing, preserved legacy model choices and per-engine budgets; software fixtures tested. |
| 0108 | 2026-09-08 | [Add a Protein Hunter design-engine checklist](lab_book/0108-protein-hunter-engine-checklist.md) | Applies the full trajectory count to each selected engine, with separate campaigns, per-engine checks and durable batch Stop/Resume; worker fixtures tested, neural acceptance pending. |
| 0107 | 2026-09-08 | [Add structure templates to Predict](lab_book/0107-predict-structure-templates.md) | Adds explicit query-chain Guide templates for Boltz, IntelliFold and Protenix v2, preserving batch scheduling and checksummed recovery; software fixtures tested, neural acceptance pending. |
| 0106 | 2026-09-08 | [Complete binding helix-control analysis](lab_book/0106-package-complete-binding-helix-analysis.md) | Replays all 840 aCbx complexes and packages the exact monomer-style 26-file report/gallery/figure/data contract without changing raw outputs. |
| 0105 | 2026-09-07 | [Target-agnostic binding helix benchmark](lab_book/0105-add-target-agnostic-binding-helix-benchmark.md) | Completes and audits the fail-closed 0-vs-1, seven-engine binding benchmark: 140/140 aCbx trajectories and 840 structures, with reusable exact FASTA/MSA input. |
| 0104 | 2026-09-07 | [Complete helix-strength analysis](lab_book/0104-analyse-complete-helix-strength-benchmark.md) | All210 trajectories and1,050 cycles audited; engine-specific structural shifts, geometry recovery, five exportable figure sets. |
| 0103 | 2026-09-06 | [Select the NISE backbone generator](lab_book/0103-select-nise-backbone-generator.md) | Adds optional RFdiffusion3 initial backbones, a 100-start default, audited diffusion batches and ESM dependency/cache reuse clarification; model fixtures tested, full neural acceptance pending. |
| 0102 | 2026-09-06 | [Separate NISE stages and add NESSO](lab_book/0102-separate-nise-stages-and-add-nesso.md) | Makes backbone and optimisation budgets explicit, exposes per-trajectory advancement, and adds optional experimental NESSO shortlisting with durable scores, isolated installation and model reuse. |
| 0100 | 2026-09-06 | [Complete monomer output inspection](lab_book/0100-inspect-complete-monomer-benchmark.md) | All 220 outcomes audited, 1,070 optimized structures; all controls analysed, inspection attrition separated from refinement effects, no default promotion. |
| 0098 | 2026-09-05 | [Package the NISE app and DMG](lab_book/0098-package-nise-app-and-dmg.md) | Refreshes the local app and unsigned-beta artifacts as 0.2.0 build 18, with NISE and Protein Hunter branding; records package verification and release limits. |
| 0099 | 2026-09-06 | [Monomer geometry rejection and continuation](lab_book/0099-diagnose-and-continue-monomer-screen.md) | Retained one invalid initialization and completed unchanged remaining controls; full results in 0100. |
| 0097 | 2026-09-05 | [Monomer core interim analysis](lab_book/0097-analyze-monomer-core-controls.md) | Five core conditions complete at n=10 each; mixed gains sheet and coil versus β-only; inspection changes 2/10 starts; expanded screen continues. |
| 0096 | 2026-09-05 | [Monomer secondary-structure benchmark](lab_book/0096-monomer-secondary-structure-benchmark.md) | Completed paired 22-condition Boltz-2 monomer screen, ten declared trajectories per condition, β-only inspection; full results in 0100. |
| 0095 | 2026-09-05 | [Monomer initialization refinement](lab_book/0095-monomer-initialization-refinement.md) | Separate assessment, regional resampling, durable attempts and explicit scheduler handoff; CLI/MCP monomer path, 14 lifecycle and 6 integration tests, no real-model efficacy claim. |
| 0095 | 2026-09-05 | [Integrate ligand NISE and rebrand Protein Hunter](lab_book/0095-integrate-ligand-nise.md) | Ports the fluorescein search and optional apo funnel into a dedicated tab, durable jobs and grouped results; distinguishes Boltz structure/affinity residency and records bounded acceptance without promoting a ligand speed claim. |
| 0094 | 2026-09-05 | [Bounded assessment journal](lab_book/0094-bounded-assessment-journal.md) | Preserves supplied attempts and eligibility/exhaustion decisions; 28 local tests pass; no adaptive generation or cycling integration. |
| 0093 | 2026-09-05 | [Coil localization and screening tools](lab_book/0093-coil-localization-and-screening-tools.md) | Long internal coil dominates the difference but confidence recovers; analysis/reference-bin tools have20 passing tests; adaptive optimization remains unimplemented. |
| 0092 | 2026-09-05 | [Sequence-first beta results](lab_book/0092-sequence-first-beta-results.md) | Both10-trajectory arms completed; mixed19.4% sheet/33.9% helix versus beta11.4%/54.1%; neither meets joint target, with lower mixed confidence. |
| 0091 | 2026-09-05 | [Sequence-first beta mask comparison](lab_book/0091-sequence-first-beta-mask-comparison.md) | Complete sequences before50% masking; both10-trajectory campaigns completed and audited; analysis in0092. |
| 0090 | 2026-09-04 | [Beta-control mechanism and mixed pilot](lab_book/0090-beta-control-mechanism-and-mixed-pilot.md) | Diagnoses missing sheet topology and temperature-amplified/conflicting priors; proposes backbone-based control and submits four bounded mixed-prior pilot trajectories. |
| 0089 | 2026-09-04 | [Secondary-structure comparison results](lab_book/0089-secondary-structure-comparison-results.md) | Audits all 300 outputs; sustained anti-helix reduces helices predominantly toward coil, while sustained beta enrichment remains unproven. |
| 0088 | 2026-09-04 | [Implement workspace recovery, durable native jobs and product boundaries](lab_book/0088-implement-product-reliability.md) | Adds recoverable archive/storage, shared native/MCP lifecycle, scoped dashboards, accessibility/recovery controls, background result loading, explicit tests and reviewed vendoring; records XCTest and GUI acceptance limits. |
| 0087 | 2026-09-04 | [Evaluate repository structure, usability, accessibility and reliability](lab_book/0087-review-repository-product-reliability.md) | Prioritizes persistence/deletion safety, shared GUI/MCP job ownership, correct workspace context, accessibility and dependable test discovery; records passing fixture contracts and untested GUI behaviour. |
| 0086 | 2026-09-04 | [Review repository handoff and active secondary-prior jobs](lab_book/0086-review-secondary-prior-handoff.md) | Confirms one running and four queued existing jobs, preserves the uncommitted feature, and records missing final-analysis endpoints without claiming a scientific effect. |
| 0085 | 2026-09-04 | [Add explicit iterative secondary-structure sequence priors](lab_book/0085-add-iterative-secondary-structure-priors.md) | Replaces a misleading helix-only control with auditable anti-helix, β-oriented and mixed priors, persists deterministic strand/turn plans across MPNN cycles, and keeps the feature experimental pending predicted-coordinate validation. |
| 0084 | 2026-09-03 | [Keep MCP result and surface-origin behavior in parity](lab_book/0084-keep-mcp-results-and-origins-in-parity.md) | Ships MCP v6 with app-equivalent iterative/RFD3 result hierarchy, run-relative artifacts, child-level verdicts, target-aligned trajectory metadata, and an enforced no-epitope whole-surface ORI contract for Codex, Claude and remote clients. |
| 0083 | 2026-09-03 | [Play target-aligned iterative cycle trajectories](lab_book/0083-play-iterative-cycle-trajectories.md) | Adds an iterative-only trajectory choice containing cycle-00 through the final design stage, rigidly fits every frame on matching target Cα atoms, exposes labelled py2Dmol scrubbing/autoplay/speed controls, and validates the complete WebKit path against the supplied campaign. |
| 0082 | 2026-09-03 | [Nest derivatives and cycles in clean result groups](lab_book/0082-nest-result-derivatives.md) | Corrects newer RFD3 manifest identity drift by deriving the parent from `backbone_pdb`, nests MPNN derivatives beneath each backbone and cycles beneath each iterative run, counts score distributions per child, and replaces cramped control-heavy comparison viewers with clean previews plus one large interactive viewer. |
| 0081 | 2026-09-03 | [Group related design results and restore saved hits](lab_book/0081-group-related-design-results.md) | Fixes the current post-check CSV parser that silently dropped all live validation rows, groups design/complex/binder-alone artifacts with scores in every results surface, restores the supplied M1 campaign's saved run-12/cycle-5 hit, and makes moved campaign folders browseable without rewriting provenance. |
| 0080 | 2026-09-03 | [Add fail-closed target templates to iterative design](lab_book/0080-add-iterative-target-templates.md) | Adds full-inference-tested target-fold guidance with Boltz, full Protenix v2, and IntelliFold v2 Flash/full; provisions pinned Kalign for Protenix, disables Boltz's geometry-breaking strong mode, preserves blind validation, and gives GUI/CLI/MCP the same checksummed fail-closed contract. |
| 0079 | 2026-09-03 | [Test 90-residue whole-surface minibinders against alpha-cobratoxin](lab_book/0079-acbx-90aa-whole-surface-campaign.md) | Runs the requested 100-backbone, ten-surface, no-hotspot 1CTX campaign with two SolubleMPNN sequences and resident Boltz holo/apo validation; records initial structural acceptance and pending results without inventing completion. |
| 0078 | 2026-09-03 | [Repair the aCbx target and RFdiffusion3 target export](lab_book/0078-repair-acbx-target-and-rfd3-export.md) | Separates exact fixed-backbone preservation from two real visual/scientific faults: an invalid bundled aCbx structure and atom14 side-chain names discarded during MLX export; replaces the target with experimental 1CTX and retains template-free verification. |
| 0077 | 2026-09-03 | [Add explicit protein-surface origin modes](lab_book/0077-add-explicit-protein-surface-origin-modes.md) | Replaces unsafe protein-COM/empty-hotspot placement with reproducible whole-surface coverage, broad-region positioning without hotspot conditioning, exact epitope hotspots, and hidden manual XYZ across GUI, MLX fixtures and MCP v5. |
| 0076 | 2026-09-03 | [Enforce RFdiffusion3 EMA weight provenance](lab_book/0076-enforce-rfd3-ema-weight-provenance.md) | Replaces the accidentally pinned raw MLX network with Foundry's verified EMA shadow artifact and makes export, installation, GUI, MCP detection and inference fail closed on provenance. |
| 0075 | 2026-09-03 | [Package RFdiffusion3 result parity for GUI and MCP](lab_book/0075-package-rfd3-result-parity-for-gui-and-mcp.md) | Builds and verifies the 0.2.0 (13) app bundle, packages MCP v4, and gives run-profile agents complete RFdiffusion3 backbone/complex/binder-alone result discovery with explicit provenance. |
| 0074 | 2026-09-02 | [Make RFdiffusion3 results complete, live and movable](lab_book/0074-make-rfd3-results-complete-and-movable.md) | Replaces popover-bound result sheets with a real window, restores generated/complex/binder-alone structures from live and completed RFD3 checkpoints, and persists the exact prediction engine and context. |
| 0073 | 2026-09-02 | [Audit executable workflows across modalities](lab_book/0073-audit-executable-workflows-across-modalities.md) | Exercises the real installed ligand RFD3→LASErMPNN boundary, eliminates cross-target fixture reuse and conformer queue collisions, and records the passing prediction, iterative, partial, motif, results, MCP, installer and Swift contracts plus explicit limits. |
| 0072 | 2026-09-02 | [Diagnose the small-molecule RFdiffusion3 launch copy failure](lab_book/0072-diagnose-small-molecule-rfd3-launch-copy.md) | Shows that the fluorescein GUI campaign stops before RFdiffusion because the small-molecule runner copies already-in-place config files onto themselves; the protein contig repair is unrelated. |
| 0071 | 2026-09-02 | [Make agent RFdiffusion3 guidance fail-safe](lab_book/0071-make-agent-rfd3-guidance-fail-safe.md) | Turns the first Claude MCP trial into enforced protein-model routing, server-served workflow guidance, derived MLX contigs, smoke-run policy and actionable managed failure logs. |
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

- [0101 — Simplify helix control and benchmark installed predictors](lab_book/0101-simplify-helix-control-and-cross-engine-benchmark.md) (2026-09-06, in progress).

- [0103 — Record geometry without rejection](lab_book/0103-record-geometry-without-rejection.md): requested advisory policy, MCP reports and full paired benchmark restart.

| Entry | Date | Work | Summary |
| --- | --- | --- | --- |
| 0152 | 2026-09-17 | [Resume biotin with stage batches](lab_book/0152-resume-biotin-with-stage-batches.md) | Interruption/affinity smoke passed; original campaign continued with stage submissions and per-input checkpoints. |
| 0153 | 2026-09-18 | [Audit student VHH budgets and results](lab_book/0153-audit-student-vhh-budgets-and-results.md) | 12 saved trajectories explain 60 cycle outputs; 756 hashes verified; dashboard aggregation and numeric commit UX remain. |
| 0154 | 2026-09-18 | [Framework budgets and combined results](lab_book/0154-framework-budgets-and-combined-results.md) | Explicit total/per-framework budgets, immediate numeric commits, combined filtered results and MCP 20; build 39 release. |
| 0155 | 2026-09-18 | [NISE live phase results](lab_book/0155-nise-live-phase-results.md) | Phase 0 checkpoint structures, phase/stage navigation, explicit checks and selection, and build 40. |
