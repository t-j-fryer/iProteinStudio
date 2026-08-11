# NanoHunter Studio — Architecture

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
Sources/NanoHunterStudio/
  Models/           value types: DesignRequest, RFD3Request, Predictor,
                    InstallComponent, DesignPoint, Project, RunPhase
  Core/             the engine (no SwiftUI):
    AppPaths          managed data dir + vendored-resource access + staging
    ScaffoldCatalog   reads examples/nanobody_scaffolds/catalog.tsv
    TemplateWriter    DesignRequest -> Boltz/NanoHunter YAML (chain A scaffold, B target)
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

Two flags Studio must **never** pass, because their defaults are the optimisation:
`--intellifold-buckets` and `--alphafold3-buckets`. Their `auto` value resolves to
the exact campaign token count, worth 2.28× and 1.58× respectively.

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

Protein targets take a shorter path — `rfd3_protein_campaign.py` → backbones and
SolubleMPNN sequences — and stop there, because re-folding a designed complex
needs a NanoHunter template and cached target MSA that cannot be derived from an
RFD3 spec.

## Data locations (managed, sandbox-friendly)

```
~/Library/Application Support/NanoHunterStudio/
  pipeline/       staged scripts + installed src/ (cloned tools)
  venvs/          NanoHunter_boltz, _ligandmpnn, _antifold, _intellifold
  projects/<slug>/<run-name>/   pipeline --out-root for each campaign
  config.json     projects + settings
```

The app **vendors** the pipeline scripts into its bundle and stages them into
the managed dir on first run, so it is independent of the NanoHunter source repo.

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
`--post-iptm-threshold` so the IntelliFold post stage matches.

## Defaults

Iterative design: Boltz-2 (design) + IntelliFold (independent check), AntiFold
designer, `--max-parallel auto` with `--throughput-profile auto`, `--resume` on.
AlphaFold 3, OpenFold-3 and the IntelliFold JAX backend are opt-in installs.

RFdiffusion3: native batch 4 across 2 concurrent shape queues, bf16, structured
folds (`is_non_loopy`) on, 4 sequences per backbone, top 100 re-folded apo.
Batch size is fixed from measurement, never derived from free memory — peak
footprint barely changes across batch sizes while throughput collapses past the
optimum, and the optimum falls as the ligand and binder grow.

## Build / distribution

- `swift build` — compiles with Command Line Tools alone.
- `./build_app.sh` — assembles a runnable, ad-hoc-signed `NanoHunter Studio.app`.
- For public distribution: open `Package.swift` in Xcode, add an app icon, and
  archive with a Developer ID certificate for notarization.

## Deliberately deferred

- FSEvents (currently 2s polling — simpler, adequate for per-cycle cadence).
- Sequence-logo / per-position views; comparison of design vs post iPTM.
- Multiple concurrent campaigns (one active run at a time for now).
- A results UI for RFdiffusion3 campaigns — rankings, apo–holo preorganisation and
  self-consistency are written to disk but must currently be opened by hand.
- NISE, and RFdiffusion3 against DNA/RNA. See LAB_BOOK.md for why.
