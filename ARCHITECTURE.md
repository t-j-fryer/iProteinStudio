# iProteinStudio — Architecture

A native macOS app that wraps the NanoHunter nanobody-design pipeline in a
friendly GUI: guided design setup, one-click install, and a **live dashboard**
with updating metrics and an in-app 3D structure viewer for hits.

Designed for a novice protein designer — no terminal, no GitHub, no manual
environment setup.

## Stack

| Concern | Choice | Why |
|---|---|---|
| UI | **SwiftUI** (SwiftPM package) | Native "double-click app"; only native GUI toolchain present on the machine. Opens in Xcode later for signing/notarization. |
| Live charts | **Swift Charts** | Native, no dependencies, updates reactively. |
| Structure viewer | **WKWebView + bundled offline 3Dmol.js** | Mature molecular rendering; fully offline (no CDN). |
| Pipeline orchestration | Foundation **`Process`** | Spawns the existing `nanohunter_run.sh`; streams stdout. |
| Live output | Timer-polled CSV reads | Runner appends per-cycle rows; polling is simple and robust. |

## Layering (UI-agnostic core + SwiftUI on top)

```
Sources/iProteinStudio/
  Models/           value types: DesignRequest, RFD3Request, Predictor,
                    InstallComponent, DesignPoint, Project, RunPhase
  Core/             the engine (no SwiftUI):
    AppPaths          managed data dir + vendored-resource access + staging
    ScaffoldCatalog   reads examples/nanobody_scaffolds/catalog.tsv
    TemplateWriter    DesignRequest -> predictor/NanoHunter YAML (chain A binder, B/C… target)
    CommandBuilder    DesignRequest -> nanohunter_run.sh argv + environment
    ProcessRunner     Process wrapper: line streaming + cancel
    RunController     campaign lifecycle: template -> spawn -> phase/log
    MetricsWatcher    tails run_*/metrics_per_cycle.csv -> [DesignPoint]
    PipelineInstaller runs setup_pipeline.sh; parses NHSTEP/NHSTATE/NHDONE/NHFAIL
                      into per-component availability; detects and links an
                      existing NanoHunter/RFD3 install
    RFD3Controller    prepares an RFdiffusion3 campaign, launches it detached,
                      polls the RFD3 repo's status script, reattaches on open
    RFD3TargetInspector  reads a target -> the sites the user may condition on
  State/AppState    root ObservableObject: projects, selection, persistence
  Views/            SwiftUI: Setup wizard, Projects sidebar, Design form,
                    LiveDashboard (Swift Charts + hits gallery), StructureViewer,
                    RFD3View (target, conditioning, sampling, progress)
  Resources/
    pipeline/       vendored NanoHunter assets + setup_pipeline.sh + PIPELINE_VERSION
    rfd3/           Studio-authored RFdiffusion3 helpers (see below)
    rfd3_overlay/   complete campaign/adaptor layer applied to pinned RFD3
    examples/       aCbx (+ shipped target MSA) and fluorescein
    web/mol/        offline 3Dmol.js + viewer.html
tools/
  sync_pipeline.sh  reproducible vendoring from a NanoHunter checkout
```

## Division of labour with the sibling repos

Studio owns the UI and input preparation. **It does not own any science**, and
that boundary is deliberate: the sibling repos encode fixes that are invisible
from outside, so a reimplementation looks correct and fails in production.

| Concern | Owner |
|---|---|
| Design scheduling, memory calibration, token bucketing, MSA rules | `nanohunter_run.sh` |
| RFdiffusion3 fixtures, binder-length arithmetic, atom preflight | `RFD3/scripts/design_from_yaml.py` |
| RFD3 → LASErMPNN → Boltz-2 affinity/apo campaign | `RFD3/scripts/run_rfd3_nise_campaign.py` |
| Predictor/designer choice, conditioning vocabulary, progress, install | Studio |

Studio must **never** pass `--intellifold-buckets`, because its `auto` default is
the validated optimisation: it resolves to the exact campaign token count. See
the measured source entry rather than inferring performance from this description.

## RFdiffusion3 flow

```
RFD3View ──▶ prepare_campaign.py
               │  SMILES -> CCD component + chain-L PDB (via prepare_ligand_target.py)
               │  conditioning -> design.yaml   (no `length`; no duplicate contig)
               │  design_from_yaml.py --stage check   preflight, GPU-free, seconds
               ▼
          launch_rfd3_nise_campaign.py   double-fork + caffeinate -dims + PID file
               │
          status_rfd3_nise_campaign.py   polled every 15 s -> stages + counts
```

The campaign outlives the app. `RFD3Controller.reattachIfRunning` picks up a
running campaign when the project is reopened.

Protein targets take a separate path — `rfd3_protein_campaign.py` generates
backbones and MPNN sequences, creates the target MSA once, builds predictor
inputs with an empty binder MSA and the real target MSA, then re-folds and ranks.
Missing alignments or requested predictors fail rather than being dropped.

## Data locations (managed, sandbox-friendly)

```
~/.iproteinstudio/
  setup_pipeline.sh + scripts/   staged pipeline and helpers
  src/            pinned upstream source checkouts
  models/         managed, verified checkpoints and model data; the isolated
                  Protenix constraint checkpoint lives in protenix_constraint/
  venvs/          NanoHunter_boltz, _ligandmpnn, _antifold, _intellifold,
                  _protenix, and the separate _protenix_constraint
  rfd3/           pinned RFdiffusion3 checkout with bundled overlay
  msa_cache/ + scaffold_msa_cache/  persistent alignments
  projects/<slug>/<run-name>/   pipeline --out-root for each campaign
  config.json     projects + settings
```

The path is deliberately space-free: Python console-script shebangs fail under
`Application Support`. The app **vendors** the pipeline, examples, IntelliFold
and Protenix MPS patches/dependency locks and RFD3 overlay into its bundle, then
stages them into the managed root, so a standalone install is independent of
sibling source repos and old home-directory model caches. Protenix Constraint is
an independent install component—venv, source and weights—because its official
v0.5 checkpoint must run with ESM disabled and cannot share the v2/Mini profile.

## Live dashboard data flow

```
DesignForm ──▶ RunController.start
                 │  TemplateWriter → <run>_template.yaml
                 │  CommandBuilder → nanohunter_run.sh --out-root … --run-name …
                 ▼
             ProcessRunner (spawn) ── stdout ─▶ log tail
                 │
   MetricsWatcher polls <run-name>/run_XXX/metrics_per_cycle.csv (every 2s)
                 │   row = cycle,iptm,plddt,confidence_json,structure_path,seq
                 ▼
             [DesignPoint] ──▶ Swift Charts (iPTM per cycle, threshold rule)
                          └──▶ hits (iptm ≥ threshold) ──▶ 3Dmol tiles (structure_path)
```

A **hit** is any design with design-stage iPTM ≥ the user's threshold
(default 0.70). The threshold is also passed to the runner as
`--post-iptm-threshold` so every selected post-prediction stage matches.

## Defaults

Iterative design: Boltz-2 (design) + IntelliFold (independent check), AntiFold
designer, `--max-parallel auto` with `--throughput-profile auto`, `--resume` on.
The default setup installs Boltz-2, AntiFold, IntelliFold PyTorch/Metal and
Protenix v2/Mini plus the unconditional MPNN family. OpenFold-3, LASErMPNN and
RFdiffusion3 are opt-in. Protenix v2/Mini is one replaceable component (shared
source, environment and chemical data) with two selectable model identities. It
owns its MSA-server route and never brings Boltz as an install dependency.
Protenix Constraint v0.5 is another opt-in component: experimental, protein-only,
design-only, isolated from v2/Mini, strict native MPS with no CPU fallback, and
ineligible as an independent checker. Its 8 Å token-centre pocket prior is not
the same quantity as Boltz's 6 Å contact setting.
IntelliFold defaults to v2-flash; full v2 is an explicit per-run choice.
AlphaFold 3 and IntelliFold JAX/Metal are retired and rejected at every launch
boundary; legacy saved projects and results remain decodable.

RFdiffusion3: native batch 4 across 2 concurrent shape queues, bf16, structured
folds (`is_non_loopy`) on, 4 sequences per backbone, top 100 re-folded apo.
Batch size is fixed from measurement, never derived from free memory — peak
footprint barely changes across batch sizes while throughput collapses past the
optimum, and the optimum falls as the ligand and binder grow.

## Build / distribution

- `swift build` — compiles with Command Line Tools alone.
- `./build_app.sh` — assembles a runnable, ad-hoc-signed `iProteinStudio.app`.
- For public distribution: open `Package.swift` in Xcode, add an app icon, and
  archive with a Developer ID certificate for notarization.

## Deliberately deferred

- FSEvents (currently 2s polling — simpler, adequate for per-cycle cadence).
- Sequence-logo / per-position views; comparison of design vs post iPTM.
- Multiple concurrent campaigns (one active run at a time for now).
- A results UI for RFdiffusion3 campaigns — rankings, apo–holo preorganisation and
  self-consistency are written to disk but must currently be opened by hand.
- NISE, and RFdiffusion3 against DNA/RNA. See LAB_BOOK.md for why.
