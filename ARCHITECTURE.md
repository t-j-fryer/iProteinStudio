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
  Models/           value types: DesignRequest, DesignPoint, Project, RunPhase
  Core/             the engine (no SwiftUI):
    AppPaths          managed data dir + vendored-resource access + staging
    ScaffoldCatalog   reads examples/nanobody_scaffolds/catalog.tsv
    TemplateWriter    DesignRequest -> Boltz/NanoHunter YAML (chain A scaffold, B target)
    CommandBuilder    DesignRequest -> nanohunter_run.sh argv + environment
    ProcessRunner     Process wrapper: line streaming + cancel
    RunController     campaign lifecycle: template -> spawn -> phase/log
    MetricsWatcher    tails run_*/metrics_per_cycle.csv -> [DesignPoint]
    PipelineInstaller runs setup_pipeline.sh, parses NHSTEP/NHDONE/NHFAIL
  State/AppState    root ObservableObject: projects, selection, persistence
  Views/            SwiftUI: Setup wizard, Projects sidebar, Design form,
                    LiveDashboard (Swift Charts + hits gallery), StructureViewer
  Resources/
    pipeline/       vendored NanoHunter assets (self-contained) + setup_pipeline.sh
    web/mol/        offline 3Dmol.js + viewer.html
```

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

## Default pipeline

Boltz (design predictor) + IntelliFold (post predictor), AntiFold designer,
auto-parallelization (`--max-parallel auto`). OpenFold and the Jupyter kernel are
intentionally excluded from the app installer.

## Build / distribution

- `swift build` — compiles with Command Line Tools alone.
- `./build_app.sh` — assembles a runnable, ad-hoc-signed `NanoHunter Studio.app`.
- For public distribution: open `Package.swift` in Xcode, add an app icon, and
  archive with a Developer ID certificate for notarization.

## Deliberately deferred

- FSEvents (currently 2s polling — simpler, adequate for per-cycle cadence).
- Sequence-logo / per-position views; comparison of design vs post iPTM.
- Multiple concurrent campaigns (one active run at a time for now).
