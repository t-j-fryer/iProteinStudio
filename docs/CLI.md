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

The app's Optimized mode selects `resident` for Boltz 2, IntelliFold v2-flash,
IntelliFold full v2, Protenix Mini and Protenix Constraint. It selects
`cycle-wave` for full Protenix v2, which was faster than residency in the paired
M4 Max campaign. Compatibility mode omits the scheduler flag and preserves the
historical per-trajectory execution route.
| `--iptm-threshold 0.7` | defines campaign hits; Studio uses the same value to gate optional checking |
| `--post-mode final-iptm` | independently checks only final-cycle designs that passed the gate; `final` checks every final design |
| `--post-mode iptm` | checks every passing optimized checkpoint from cycle 01 onward; use `all` instead of `iptm` to disable the threshold gate |
| `--post-include-cycle00` | advanced CLI diagnostic opt-in for also checking the unoptimized seed; Studio never emits it |
| `--model v2-flash` | choose `v2-flash` or the larger full `v2` IntelliFold model; omit when IntelliFold is not used |

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

New iterative campaigns also copy the small app-owned runner/policy layer into
`<campaign>/.studio_runtime/pipeline` and record that path in `studio_run.json`.
Resume therefore uses the exact code snapshot that started the campaign and
fails loudly if it is missing, instead of silently adopting a later app update.
