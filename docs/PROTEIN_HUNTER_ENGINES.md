# Choosing design engines in Protein Hunter

**Design engines** is a checklist in both Quick and Advanced setup. Tick each
engine you want to use, then set **Trajectories per engine** and **Optimization
cycles**. Every selected engine runs the specified settings with the full
trajectory count. The count is never divided among the engines.

For example, 12 trajectories per engine, three engines and five cycles means:

- 12 trajectories for each engine, or 36 trajectories overall;
- 180 optimized structures across cycles 01–05;
- another 36 cycle-00 starting structures, excluded from the optimized total.

These are requested budgets. A failed or interrupted campaign may produce fewer
structures; independent checks add predictions according to their own settings.
The form shows the total before you start. An empty checklist cannot start.

For nanobodies, a second checklist selects scaffolds. The per-engine budget is
split across those scaffolds, equally by default or with custom counts. Every
engine receives the same allocation, and each engine–scaffold pair is a separate
saved campaign. See [nanobody scaffolds and budgets](NANOBODY_DESIGN.md).

## OpenFold-3 and IntelliFold checkpoints

OpenFold-3, IntelliFold v2 Flash and IntelliFold v2 Full are separate design
choices. You can select all three in one batch; each gets the full trajectory
budget and its own results. Both IntelliFold choices use the existing PyTorch
runner, with an explicit `v2-flash` or `v2` checkpoint in each saved command.

Full requires the optional IntelliFold full-v2 checkpoint and its shared runtime
from Engines. OpenFold-3 requires its existing engine installation. A missing
installation disables the corresponding new selection. Template guidance remains
available for both IntelliFold checkpoints; OpenFold-3 does not accept Guide
PDB/CIF templates in this workflow and remains disabled while one is selected.

The **IntelliFold checking model** control applies to independent checks only.
It does not change the Flash/Full design checkboxes. Flash and Full belong to the
same model family and are not treated as independent validators of one another.
Older workspaces with a shared IntelliFold model setting retain their previous
Flash or Full choice when opened. A batch containing Full has no time estimate
because the existing Flash timing is not a Full-model benchmark.

## Shared settings and independent checks

Target, template, binder/scaffold settings, sequence designer, temperatures,
cycle count and hit/check settings apply to each engine campaign. The batch
records one random base seed for all its campaigns; different engines can still
produce different structures and subsequent trajectories. Engine-specific
capabilities and existing scheduling defaults remain in force.

**Check hits with** is a separate checklist. For each campaign, Studio excludes
that campaign's design model from its independent checkers. A selected design
model can still check another model's campaign. Boltz with and without steering
potentials count as the same model for this independence rule. The form shows
which checkers each campaign will actually use, including campaigns with no
independent checker selected.

Missing engines cannot be newly selected. Saved missing/retired selections and
incompatible targeting settings block Start until corrected. Guide templates
remain limited to their supported engines. Epitope guidance remains engine
specific; engines that do not support it keep the saved hotspots dormant, as in
single-engine Protein Hunter. Ligand atom restraints remain a hard compatibility
requirement. The checklist identifies incompatible choices rather than silently
removing a selected campaign.

## Queue, progress and results

One click saves every campaign before submitting a single durable engine-batch
job. Engines then run in checklist order, one after another, through the shared
Studio execution lock. Within each engine, the existing policy is preserved:
Protenix v2 uses directory waves per cycle; the other design engines use the
existing resident-worker policy. Selecting more engines adds work; it does not
load every model onto the GPU at once. No new throughput benchmark is claimed.

The live dashboard follows the active engine and labels its position in the
batch. Its counts and structures describe that engine. Each engine also has its
own campaign entry and results in Activity/history, with the engine in the
folder name. A completed engine stays completed if a later engine fails.

**Stop** stops the active engine and prevents later engines from starting.
**Retry/Resume** continues the saved batch, skipping completed engines after
verifying their recorded artifacts. The interrupted engine uses the existing
per-cycle resume checkpoints. Resume uses saved commands, inputs and immutable
pipeline snapshots; changing today's form does not change that batch. Start a
new batch to use different settings. Closing Studio leaves the durable worker
running, and reopening reattaches to it.

## On-disk contract

The workspace contains a batch directory with `studio_engine_batch.json` and
`engine_batch_progress.json`, plus separate sibling engine campaign directories.
Each engine retains its own `studio_run.json`, input files and `.studio_runtime`
snapshot. The batch manifest records all campaign paths, labels and the budget
per engine. The broker preflights every child and fingerprints every child's
scripts and inputs before execution. Completed-engine receipts hash durable
result artifacts; missing or altered outputs prevent a silent skip on Resume.

Multi-scaffold batches use manifest version 2, recording each child's trajectory
budget, engine ID and scaffold ID. Preflight checks those values against the
saved child requests and commands, and requires identical scaffold allocations
for every engine. Existing version-1 batches remain supported.

Older workspaces without a checklist retain their previous single design engine.
Single-engine campaigns and old run manifests remain resumable. The multi-engine
operation is a native Studio batch adapter; existing public iterative CLI/MCP
single-engine contracts remain unchanged.

See [Lab Book 0108](../lab_book/0108-protein-hunter-engine-checklist.md) for tests
and limitations. Tests exercise real broker workers with inert engine scripts;
this change has not been evaluated in a new neural-inference campaign.
