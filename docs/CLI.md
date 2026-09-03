# Running everything from the command line

The app is a front end. Everything it does is a script you can run yourself, and
the app writes its settings to disk before running them — so any run started in
the UI can be repeated, inspected, or scripted without it.

Throughout, `$ROOT` is the managed installation:

```bash
export ROOT="$HOME/.iproteinstudio"        # created by the app on first launch
export NANOHUNTER_ROOT="$ROOT"             # the pipeline reads this
```

Every environment lives in `$ROOT/venvs/`, every model repo in `$ROOT/src/`,
weights in `$ROOT/models/`, and RFdiffusion3 in `$ROOT/rfd3/`.

## AI agents: Model Context Protocol

iProteinStudio ships one dependency-free MCP implementation with three
least-privilege profiles. Codex and Claude Code use the same server and schemas;
only their configuration file formats differ.

| Profile | Intended access |
|---|---|
| `read` | Installed engines, projects, runs, manifests, bounded logs and normalized result tables |
| `run` | Content-addressed input import, target inspection, immutable preflight plans, scientific jobs, cancellation and resume |
| `admin` | Engine installation/repair and verified storage maintenance; disabled by default |

Configure a trusted project after launching the app once, which stages the
bridge at `$ROOT/mcp/`:

End users do not need these commands. The workspace toolbar's **AI** button and
**Settings → AI assistants** install/remove user-level Codex and Claude Desktop
registration after the user chooses `read` or `read + run`. The configuration
utility remains the reproducible automation and troubleshooting route.

```bash
# Preview both changes first.
/usr/bin/python3 "$ROOT/mcp/configure.py" \
  --client both --scope project --project-root /path/to/trusted/project

# Apply after review.
/usr/bin/python3 "$ROOT/mcp/configure.py" \
  --client both --scope project --project-root /path/to/trusted/project --write
```

The normal configuration advertises `read` and `run`. Administration requires
both an explicit profile and an environment opt-in:

```bash
IPROTEINSTUDIO_ENABLE_ADMIN_MCP=1 \
  /usr/bin/python3 "$ROOT/mcp/configure.py" \
  --client codex --scope project --project-root /path/to/trusted/project \
  --profiles read,run,admin --write
```

The configuration writer preserves unrelated Codex TOML and Claude MCP entries.
It writes resolved paths only into the user's generated configuration; no
machine-specific path is part of shipped source.

### Execution contract

Long tool calls do not hold an MCP request open. A workflow uses:

1. Call `workflow_guide` for the intended workflow. This returns Studio's
   model-routing rules, defaults, smoke-test policy and common scientific traps
   inside the protocol, so the advice is identical in Codex, Claude Code and
   desktop clients.
2. Call `prediction_plan`, `target_prepare_plan`, `iterative_design_plan`, or one of
   the three mode-specific RFD3 plan tools.
3. Review the normalized request, exact command preview, input/script hashes and
   output location.
4. Pass both returned `plan_id` and `plan_sha256` to `job_start`.
5. Poll with `job_status` or the bounded `job_wait`; use `job_resume` after an
   interruption.
6. Call `results_overview` to recover scientific parentage and saved verdicts,
   then use `results_query` only when raw table columns or a numeric
   distribution are needed.

For any new target/settings combination, first complete a 1–5-backbone
end-to-end smoke campaign with the same sequence designer and predictors. A
failed job returns the actionable message plus `pipeline_log_tail` and
`worker_log_tail`; `run_status` also returns the newest RFdiffusion3 stage logs.
Read those fields before changing scientific parameters, and do not ask the user
for arbitrary folder access to diagnose a managed run.

Plans are immutable. `job_start` recalculates the plan digest and verifies every
recorded runner before launching. If an app update changed a script after
preflight, the job fails and requires a new plan rather than silently using new
scientific code.

Each MCP client has its own local stdio server process, but every scientific or
administration worker uses `$ROOT/agent/execution.lock`. Codex, Claude and the
direct `studioctl.py` route therefore cannot launch overlapping Apple-GPU jobs.
The lock serializes jobs conservatively; scheduling *within* an iterative or
RFD3 verification campaign remains the validated resident/cycle-wave policy of
the underlying runner.

The existing GUI launch path is intentionally unchanged and does not acquire
this agent lock. Do not start a GUI campaign while an agent job is active (or
vice versa); `studioctl.py jobs` is the authoritative agent-job check. Moving
the GUI itself behind the broker would change validated interactive launch
semantics and requires a separate migration and performance validation.

The detached worker, plan, status, logs and audit records live under
`$ROOT/agent/`. Closing the MCP client does not stop the job. Cancellation sends
SIGTERM to the worker process group, not just its immediate model process.

### Scientific tools

- `target_inspect` uses the same exact target/RFD3 atom vocabulary as the GUI.
- `prediction_plan` preserves per-chain `auto`, `empty`, or exact imported MSA
  policy and never silently converts an alignment failure to single-sequence.
- `iterative_design_plan` accepts only an allowlisted scientific argument set.
  Studio supplies output paths, snapshots, `--resume`, memory policy, and the
  measured resident/cycle-wave scheduler. Optional `target_template_path`
  accepts PDB/CIF/mmCIF and `target_template_mode` is `guide`. Guide mode
  supports Boltz-2, Protenix v2, and IntelliFold v2 Flash/full. The broker
  stages the imported structure before launch and never templates binder A or
  independent validation predictions.
- `rfd3_denovo_plan`, `rfd3_partial_diffusion_plan`, and
  `rfd3_motif_scaffolding_plan` are separate so their incompatible semantics
  cannot be mixed. Partial diffusion constrains `partial_t` to 0.1–15 Å and
  removes de-novo origin overrides. Motif scaffolding requires a non-empty atom
  selection for every source motif residue.
- Protein de-novo campaigns default to SolubleMPNN, not LASErMPNN or
  LigandMPNN. Clients should omit `contig`; Studio derives the pinned adapter's
  binder-first comma-delimited form from the binder-length bin and normalized
  target chains. Every candidate is sequence-designed and independently
  predicted before ranking; RFdiffusion3 internal scores are not a prefilter.
- `results_overview` mirrors the native result hierarchy. Iterative results are
  run → ordered cycle → design/complex-reprediction/binder-alone artifacts;
  its trajectory contains only design-stage cycles and records the GUI's
  target-chain Cα alignment contract. RFdiffusion3 results are generated
  backbone → MPNN derivative → complex/binder-alone validation. Saved hits
  belong to checked cycles or derivatives, never automatically to the parent.
  Returned structure paths are verified relative to the managed run.
- `results_query` follows the overview when an agent needs a recognized raw
  table, hit-only rows, or a bounded numeric distribution. It does not invent
  missing metrics.

There is deliberately no arbitrary shell, Python, executable, environment,
RFD3-YAML, file deletion, or raw engine-argument tool. External inputs are
copied into checksum-addressed managed storage. Additional import roots must be
added explicitly to `$ROOT/agent/policy.json`.

The same implementation has a direct JSON CLI for diagnostics and automation:

```bash
/usr/bin/python3 "$ROOT/mcp/studioctl.py" doctor
/usr/bin/python3 "$ROOT/mcp/studioctl.py" detect
/usr/bin/python3 "$ROOT/mcp/studioctl.py" projects
/usr/bin/python3 "$ROOT/mcp/studioctl.py" runs --project my-project
/usr/bin/python3 "$ROOT/mcp/studioctl.py" jobs
```

`doctor` is offline and checks that all three privilege profiles and every
versioned request schema can load. `detect` then checks the managed engines.

### ChatGPT, remote clients and phone delegation

ChatGPT cannot start the laptop's local stdio server from OpenAI's infrastructure.
iProteinStudio therefore ships a separate opt-in Streamable-HTTP boundary. The
AI settings screen can start or stop it; the gateway remains loopback-only,
capability-authenticated, limited to `read` or `run`, and keeps the Mac awake
while active. It never exposes administration.

That local listener is not a public endpoint. A trusted HTTPS tunnel or hosted
relay must forward its port before ChatGPT can connect. Enter the resulting
public HTTPS base in the app to copy a complete capability-bearing MCP URL, then
add that URL in ChatGPT using the documented custom-app flow. Treat the URL like
a password: its path is the credential and may otherwise leak through proxy
access logs. Stopping the gateway revokes the live listener; rotating its token
invalidates the old URL.

Starting the gateway also rotates its capability URL, including when switching
from read-only to run access. An old read-only URL can never silently gain write
privileges.

The application intentionally does not choose, install or authorize a tunnel
provider. That action changes external network state and needs a separate user
choice. A future hosted Studio relay could remove this last infrastructure step
while retaining account authentication and revocation.

---

## Install

```bash
# Everything
bash "$ROOT/setup_pipeline.sh" --all

# Or pick engines individually
bash "$ROOT/setup_pipeline.sh" --with-boltz --with-intellifold --with-rfd3

# Add only optional checkpoints to their shared runtimes
bash "$ROOT/setup_pipeline.sh" --with-boltz-affinity \
  --with-intellifold-full --with-protenix-mini

# Add the experimental, design-only protein-epitope checkpoint
bash "$ROOT/setup_pipeline.sh" --with-protenix-constraint

# What is present
bash "$ROOT/setup_pipeline.sh" --detect

# List every supported component and its scope
bash "$ROOT/setup_pipeline.sh" --help

# Reuse an existing NanoHunter installation instead of downloading again
bash "$ROOT/setup_pipeline.sh" --link-existing ~/NanoHunter --link-rfd3 ~/RFD3

# Turn links into real local copies
bash "$ROOT/setup_pipeline.sh" --materialise

# Consolidate only checksum-verified duplicate managed assets
bash "$ROOT/setup_pipeline.sh" --minimize-storage
```

AlphaFold 3 and `intellifold-jax` are retired. Setup and run entry points reject
their old flags explicitly; IntelliFold's supported backend is PyTorch/Metal.

`--with-boltz` installs structure prediction without the optional affinity
checkpoint. `--with-intellifold` installs v2 Flash without full v2.
`--with-protenix-v2` and `--with-protenix-mini` independently add those
checkpoints over one shared Protenix runtime; the legacy `--with-protenix`
selects both.
`--with-protenix-constraint` is deliberately separate: it creates
`venvs/NanoHunter_protenix_constraint`, `src/ProtenixConstraint` and
`models/protenix_constraint`, downloads and SHA-256 verifies
`protenix_base_constraint_v0.5.0.pt`, and writes an install receipt recording the
pinned source, patch, dependencies, checkpoint and native-MPS/no-fallback policy.
It does not install ESM weights. `--all` includes both Protenix components.

Setup is serialized by `$ROOT/.install.lock`: a second app copy or CLI setup
fails before changing an environment, while a lock whose recorded process no
longer exists is recovered automatically. The installer keeps macOS awake.
Every managed checkpoint transfer, including IntelliFold and OpenFold, retains a
resumable `.part` and goes through the same timeout-aware SHA-256 verifier. No
final checkpoint is exposed before its pinned digest passes. GUI installs write complete logs under
`$ROOT/logs/installer/`; the Engines screen can reveal the current log. Detection
distinguishes an absent component from an incomplete install or broken link, and
reports a runtime-contract update where a component has a comprehensive receipt.

The installer runs a checksum-pinned uv build and exact CPython patch versions
from `$ROOT/toolchains`, never an ambient developer Python. Studio-managed
engine environments use complete hash-locked package graphs. RFdiffusion3's
upstream nested environment retains exact direct pins plus a pinned Foundry
commit, but does not yet have a fully hashed transitive graph. New environments are built and health-
checked under `$ROOT/components/<engine>/versions/`, then atomically switched into
the familiar `$ROOT/venvs/` path; the prior environment is retained if a switch
fails. Receipts under `$ROOT/receipts/` record Python, the complete resolved
package graph, source revision plus validated patch state, artifacts and device
policy. Protenix v2/Mini and Constraint keep isolated imports while referring to
one verified chemical-data copy under `$ROOT/shared/protenix-common/`. Package
installation uses uv's macOS copy-on-write clone mode and a Studio-owned cache;
clearing that cache cannot invalidate an environment. Pinned source checkouts
share a managed Git object store while retaining independent patched worktrees.
The Engines screen's **Minimize duplicate assets** action migrates older
Protenix installs only when the complete generated file set matches the pinned
SHA-256 manifest; modified or unknown files are retained.

Before a GUI install starts, Studio shows the aggregate approximate installed
footprint and requires that amount plus a 3 GB operating-system/temporary-file
reserve. Cancel waits for the installer process tree—not merely its parent
shell—to stop before setup controls become available again.

**The install path must not contain a space.** A Python console script carries an
absolute shebang and the kernel splits it on whitespace, so a venv under
`~/Library/Application Support/…` produces `bad interpreter`. The installer
refuses such a path.

---

## Predict a batch of sequences

Two steps: turn sequences into jobs, then fold them.

```bash
# Sequences -> jobs. Modes: monomer | shared | paired
"$ROOT/venvs/NanoHunter_boltz/bin/python" "$ROOT/rfd3_scripts/parse_sequences.py" \
  designs.fasta --mode shared --partner "$TARGET_SEQUENCE" \
  --binder-msa empty --partner-msa auto > jobs.json
```

`--binder-msa empty` is the right choice for anything designed: a de-novo binder
has no homologues, so an alignment costs a server round trip and adds nothing.

```jsonc
// config.json
{
  "root": "…/.iproteinstudio",
  "output": "…/my_batch",
  "predictors": ["boltz"],           // boltz | protenix-v2 | protenix-mini | intellifold | openfold-3-mlx
  "intellifold_model": "v2-flash",  // v2-flash | v2; IntelliFold PyTorch/Metal
  "use_potentials": false,
  "affinity": false,                 // Boltz only, small molecules only
  "max_parallel": 0,                 // 0 = the measured optimum per engine
  "batch_size": 0,
  "msa": {
    "cache_dir": "…/.iproteinstudio/msa_cache",
    "index_roots": ["…/.iproteinstudio/msa_cache", "…/.iproteinstudio/projects"],
    "allow_server": true             // false = fail rather than fetch
  },
  "jobs": [ /* from parse_sequences.py */ ]
}
```

```bash
"$ROOT/venvs/NanoHunter_boltz/bin/python" "$ROOT/rfd3_scripts/predict_batch.py" \
  --config config.json
```

Results land as `predictions.csv`, `run_summary.json` and per-engine folders.

Every alignment on the machine is indexed by the sequence it describes, so a
target aligned once during a design campaign is never aligned again. A Protenix
prediction uses upstream `protenix msa` on a cache miss; other selections use
Boltz's ColabFold client. Neither route needs local genetic databases, and a
failed requested search stops rather than degrading to single-sequence mode.

New GUI batches are stored under
`projects/<slug>/prediction_runs/prediction-<timestamp>/`; the older single
`predictions/` directory is still discovered by run history.

---

## Iterative design

The design tabs drive `nanohunter_run.sh`. The app prints the exact command it
used into both the live log and the campaign's durable `studio.log`. It also
writes `studio_run.json` beside the output; Activity uses that exact manifest
for Resume rather than rebuilding settings from the current form. A minimal
example:

```bash
"$ROOT/nanohunter_run.sh" \
  --workflow protein --predictor boltz --sequence-designer solublempnn \
  --template-yaml my_target.yaml --run-name my_campaign \
  --target-template known_target_fold.cif --target-template-mode guide \
  --num-runs 20 --num-opt-cycles 5 \
  --iptm-threshold 0.7 \
  --model v2-flash \
  --random-binder --binder-min-len 60 --binder-max-len 120 \
  --post-predictor intellifold --post-mode final-iptm --post-iptm-threshold 0.7 \
  --target-msa-mode auto --target-msa-generator auto --require-target-msa \
  --max-parallel auto --throughput-profile auto --resume
```

Flags worth knowing:

| Flag | Why |
|---|---|
| `--require-target-msa` | an unreachable MSA server otherwise degrades the run to single-sequence silently |
| `--throughput-profile auto` | uses a measured per-machine schedule, and *rejects* one from a different Mac |
| `--resume` | idempotent; reuses completed cycles after an interruption |
| `--design-scheduler cycle-wave` | one directory predictor process per cycle for supported iterative engines |
| `--design-scheduler resident` | one live model across cycles; requires `--max-parallel 1 --wave-batch-size all` |
| `--iptm-threshold 0.7` | defines campaign hits; Studio uses the same value to gate optional checking |
| `--post-mode final-iptm` | independently checks only final-cycle designs that passed the gate; `final` checks every final design |
| `--post-mode iptm` | checks every passing optimized checkpoint from cycle 01 onward; use `all` instead of `iptm` to disable the threshold gate |
| `--post-include-cycle00` | advanced CLI diagnostic opt-in for also checking the unoptimized seed; Studio never emits it |
| `--model v2-flash` | choose `v2-flash` or the larger full `v2` IntelliFold model; omit when IntelliFold is not used |
| `--target-template PATH` | guide target protein chains from an immutable PDB/CIF copy during design cycles; binder and validation refolds remain untemplated |
| `--target-template-mode guide` | ordinary template conditioning; supported by Boltz-2, Protenix v2, and IntelliFold v2 Flash/full |

Target templates are deliberately narrower than generic predictor input. Guide
mode maps only target chains (B/C/...) from the supplied PDB/CIF; chain A, the
designed binder, receives no template. Boltz's upstream strong coordinate
potential is intentionally unavailable because two Apple-GPU acceptance runs
reproducibly generated broken target peptide geometry. Studio
rejects Protenix Mini/Constraint, ligand campaigns, missing files,
and incompatible modes instead of silently ignoring the request. OpenFold-3 is
not part of iterative design. Every accepted template is copied into the
campaign, checksummed, and recorded in `target_template_provenance.json`.
For Boltz, Studio also derives and records a normalized mmCIF prediction input;
this fills missing polymer metadata in atom-only PDBs without changing the
preserved source artifact. For IntelliFold, Studio deterministically matches
each target sequence to a template chain, emits the HMMsearch-style A3M and
normalized mmCIF that upstream requires, and bypasses only the database-search
duplicate/date filters for that checksummed local template. This explicit path
does not download IntelliFold's optional PDB template database.

The app always selects `resident` for Boltz 2, IntelliFold v2-flash,
IntelliFold full v2, Protenix Mini and Protenix Constraint. It selects
`cycle-wave` for full Protenix v2, which was faster than residency in the paired
M4 Max campaign. Scheduling is not a GUI preference: direct CLI users can still
pass `--design-scheduler run` explicitly to reproduce or diagnose the historical
per-trajectory route, while an existing campaign Resume reuses its recorded
command unchanged.

For target proteins, Studio's prediction, target-preparation, RFdiffusion3, and
iterative-design workflows all reuse an A3M only when its first record exactly
matches the requested sequence and it contains at least two records. They search
the managed `msa_cache`, bundled examples, projects, and prior outputs before
requesting a new alignment. A newly generated iterative-design alignment is
published back to the managed cache for the other workflows.

The GUI accepts a protein complex as one colon-separated value, for example
`CHAIN_ONE:CHAIN_TWO`. Predict assigns those subunits A/B in input order.
Iterative design and RFdiffusion3 reserve A for the designed binder, so fixed
targets become B/C/D. Every target subunit owns a separate query-matched MSA;
the runner rejects an ambiguous single `--target-msa-path` for a multimer rather
than applying one chain's alignment to every chain. In hand-written iterative
YAML, put the appropriate `msa:` path on each target protein entry.

For protein multimers, Boltz, IntelliFold and Protenix confidence JSONs include
`ipsae_min`, `ipsae_directional` and `ipsae_pairs`. `ipsae_min` is the smaller
directional score for a two-chain interface; with more chains it is the weakest
pairwise minimum. OpenFold-3 does not receive an ipSAE value because it emits
PDE rather than PAE. RFdiffusion3 protein outputs retain per-engine, mean and
minimum ipSAE(min) diagnostics but continue to rank by their established mean
iPTM unless that policy is separately validated and changed.

Leave `--intellifold-buckets` alone for established runs. Its `auto` default
resolves to the exact campaign token maximum, which is the single largest
measured IntelliFold speed-up available. `length-aware` is an experimental
variable-length mode with 32-token total-length bands ending at the exact
maximum; it is reserved for the 65–150-aa minibinder validation until measured.

### Experimental Protenix Constraint pocket proposals

Install the separate component above, select target residues in the same chain
notation used by the GUI, and choose the dedicated design engine:

```yaml
nanohunter:
  target_epitope_residues: [B34, B35]
  protenix_pocket_max_distance: 8.0
sequences:
  - protein: {id: A, sequence: GGGGGGGGGG, msa: empty}
  - protein: {id: B, sequence: HIKLMNPQRSTVWY, msa: target.a3m}
version: 1
```

```bash
"$ROOT/nanohunter_run.sh" \
  --workflow protein --predictor protenix-constraint-v0.5 \
  --sequence-designer solublempnn --template-yaml constraint_target.yaml \
  --run-name constraint_campaign --num-runs 20 --num-opt-cycles 5 \
  --target-msa-mode auto --target-msa-generator auto --require-target-msa \
  --post-predictor boltz --post-mode final-iptm --resume
```

This route is protein-only and proposal-only. The adapter strict-loads the
official v0.5 constraint checkpoint with ESM disabled, asserts native MPS, and
uses the validated upstream 10 recycle × 200 sampling-step profile. The 8 Å
value is a learned protein-token-centre (Cα) pocket prior, not the nearest-heavy-
atom cutoff used to describe a physical contact. It is not interchangeable with
Studio's 6 Å Boltz contact setting. The initial paired acceptance produced only
weak alternative-pocket steering, so the engine remains explicitly experimental
and cannot be selected as a post-predictor. Re-fold final designs with an
independent unconstrained engine and inspect the resulting interface geometry.

The managed patch also recognizes the exactly absent substructure channel used
by pocket-only jobs. Upstream otherwise expands that zero feature into N²
Transformer tokens and N⁴ attention memory. Studio evaluates the single
checkpoint-defined zero-token value and broadcasts it; nonzero substructure
constraints retain the upstream path. The official checkpoint's explicit and
shortcut paths agree within 1e-6 on native-MPS validation cases. Setup hashes
this patch into the install receipt and marks older runtimes as needing repair;
valid weights are kept.

To target specific atoms of a small molecule, get the names Boltz will use —
**they change when the affinity head is on**, because it standardises the SMILES
first:

```bash
"$ROOT/venvs/NanoHunter_boltz/bin/python" "$ROOT/rfd3_scripts/boltz_ligand_atoms.py" \
  'O=C(NCCO)c1ccc…' 1        # 1 = affinity head on
```

then write them into the template as a `pocket` constraint and run with
`--boltz-use-potentials` — without potentials a forced constraint barely steers.

Protein hotspot residues use the same high-level `nanohunter.target_epitope_residues`
field for every binder type. `boltz_contact_mode: auto` resolves to a pocket plus
CDR3-centre contact for nanobodies, and to the generic binder-pocket restraint
for mini-binders and peptides when Boltz is selected. Protenix Constraint v0.5
maps the same residues to its separate learned pocket prior. Other engines design
against the full target: Studio keeps entered hotspots visible but dormant, and
the CLI rejects any request that would silently claim to apply an unsupported
restraint.

---

## RFdiffusion3

Studio separates RFdiffusion3 into three input contracts: **De novo design**,
**Partial diffusion**, and **Motif scaffolding**. The latter two accept an
existing complex, normalize the diffused/source chain to A and keep target
chains fixed as B/C/D…. In the app, each has a one-click p53–MDM2 worked
example based on the bundled 1YCR coordinates. Partial diffusion uses
`partial_t` as coordinate-noise standard deviation in Å. Motif scaffolding
requires an explicit atom list for every unindexed motif residue; Studio does
not rely on Foundry's broader default atom mask.

Protein de-novo placement has four explicit modes. `surface_scan` is the
default when no binding site is known: Studio calculates solvent-accessible
patches, places outward `ori_token` centres, and divides the exact backbone
quota across immutable per-ORI fixtures. `surface_patch` calculates one outward
centre from broad user-selected residues but does not turn those residues into
hotspots. `targeted_epitope` uses reviewed residues as real Foundry hotspots.
`manual` exposes exact XYZ coordinates as a collapsed expert control. A fixed
protein's centre of mass is never used as the unspecified-site fallback.

```bash
cd "$ROOT/rfd3"

# Understand the ligand first: chemistry checks, which shapes it adopts,
# how the design budget should be split
"$ROOT/rfd3/.venv/bin/python" "$ROOT/rfd3_scripts/ligand_intelligence.py" request.json

# Prepare a campaign from a Studio request (fast, no GPU; runs the atom preflight)
.venv/bin/python "$ROOT/rfd3_scripts/prepare_campaign.py" studio_request.json

# Launch detached under caffeinate, and watch it
.venv/bin/python scripts/launch_rfd3_nise_campaign.py --config campaign.json
.venv/bin/python scripts/status_rfd3_nise_campaign.py --config campaign.json
```

Backbones alone, from a design YAML:

```bash
.venv/bin/python scripts/design_from_yaml.py spec.yaml \
  --lengths 65,84,103,122,150 --num-designs 1000 \
  --batch-size 4 --queues-per-bin 2 --precision bf16
```

`--lengths` means *binder* residues. Foundry's own `length` is the total
component count, so a fixed motif in the contig is added on — `design_from_yaml`
does that for you, which is why you should not write `length` into the spec.

Design across several ligand conformers, splitting the budget:

```bash
.venv/bin/python scripts/design_from_yaml.py spec.yaml \
  --conformers A.pdb:0.5:A,B.pdb:0.3:B,C.pdb:0.2:C --lengths 65,100,150
```

For a conjugated ligand, `request.json` records a *directed bond*, not one
ambiguous attachment atom:

```json
{
  "smiles": "...",
  "attachment_atom": 9,
  "attachment_linker_atom": 8,
  "search_pdb": true,
  "output_dir": ".../conformers"
}
```

Both numbers are zero-based indices in the submitted SMILES atom order. The
first endpoint remains in the recognition core; the directly bonded second
endpoint identifies the linker side to exclude from shape clustering. Studio's
annotated drawing shows these indices before inspection and the exact RFD3 atom
names after inspection, so the two numbering systems are never conflated.

Ligand conditioning follows Foundry's target-atom semantics:

- **Bury / expose** controls relative solvent accessibility (RASA). Bury asks
  for pocket packing; expose keeps a linker or handle solvent-accessible.
- **Hotspot** asks for a designed heavy atom near the selected target atom
  (typically within 4.5 Å); it does not require enclosing that atom.
- **Ligand donor / acceptor** describes the selected ligand atom. RFdiffusion3
  places the complementary protein acceptor / donor respectively.

Studio derives donor and acceptor proposals with RDKit for the exact tautomer
and protonation supplied, proposes burial only for neutral carbon/halogen core
atoms, never guesses hotspots, and shows a preview before replacing the current
conditions. Experimental PDB evidence is accepted only when the full InChIKey
matches, including stereochemistry and protonation.

New GUI campaigns live under
`projects/<slug>/rfd3_runs/rfd3-<timestamp>/`. Protein-target campaigns write
`campaign_progress.json` and accept `--resume`; the Activity panel detects the
PID, checkpoints and final `analysis/top100.csv`. Existing `projects/<slug>/rfd3`
campaigns remain visible as legacy history.

The RFdiffusion3 results sheet is live. It discovers each append-only accepted
backbone checkpoint and each successful verification structure without waiting
for final ranking, refreshes while the run is active, and provides Overview,
Structures and Hits views. Overview plots distributions of whichever saved
metric is selected. Motif rows display the source → designed residue mapping;
independent predictions are globally fitted on the explicitly constrained motif
atoms before overall and per-residue motif RMSDs are calculated. The generated
backbone's pre-copy insertion-assignment RMSD is shown separately and is not
mistaken for post-prediction motif recovery.

---

## Where things go

```
$ROOT/
  setup_pipeline.sh          installer
  nanohunter_run.sh          design runner
  scripts/                   pipeline helpers
  rfd3_scripts/              prediction, ligand analysis, campaign preparation
  rfd3/                      RFdiffusion3 + its script overlay
  venvs/  src/  models/      environments, code, weights
  toolchains/                 checksum-pinned uv and exact managed CPython builds
  components/*/versions/     staged/versioned engine environments
  receipts/                  verified package/source/artifact/device manifests
  shared/protenix-common/     one verified chemical-data copy for Protenix products
  cache/{uv,pip}/             Studio-owned download/build caches (safe to clear)
  objects/sha256/             immutable content-addressed A3Ms
  objects/pipeline/sha256/    exact app policy snapshots, stored once per version
  msa_cache/                 shared alignments, indexed by sequence
  scaffold_msa_cache/        bundled deep MSAs for all seven nanobody scaffolds
  logs/installer/            durable setup and repair logs
  projects/<slug>/           durable, separately timestamped run outputs
```

Protenix Constraint uses the explicit `_protenix_constraint`,
`ProtenixConstraint` and `protenix_constraint` entries under `venvs/`, `src/`
and `models/`, respectively. Removing that component from the Engines screen
deletes only those managed runtime assets; workspaces, results and cached MSAs
are retained.

New iterative campaigns APFS-clone the small app-owned runner/policy layer from
its content-addressed object into `<campaign>/.studio_runtime/pipeline` and
record that path in `studio_run.json`. The clone is independently mutable but
shares physical blocks until changed. Resume therefore uses the exact code
snapshot that started the campaign and fails loudly if it is missing, instead
of silently adopting a later app update. Detailed output retention and sampling
provenance are specified in [Output storage and retention](OUTPUT_STORAGE.md).
