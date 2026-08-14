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

# What is present
bash "$ROOT/setup_pipeline.sh" --detect

# Reuse an existing NanoHunter installation instead of downloading again
bash "$ROOT/setup_pipeline.sh" --link-existing ~/NanoHunter --link-rfd3 ~/RFD3

# Turn links into real local copies
bash "$ROOT/setup_pipeline.sh" --materialise
```

AlphaFold 3 weights are never downloaded — obtain `af3.bin` from Google and put
it at `$ROOT/models/alphafold3/af3.bin`.

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
  "predictors": ["boltz"],           // boltz | intellifold | intellifold-jax
                                     // alphafold3 | openfold-3-mlx
  "intellifold_model": "v2-flash",  // v2-flash | v2; applies to PyTorch + JAX
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
target aligned once during a design campaign is never aligned again.

---

## Iterative design

The design tabs drive `nanohunter_run.sh`. The app prints the exact command it
used into the run log; copy it. A minimal example:

```bash
"$ROOT/nanohunter_run.sh" \
  --workflow protein --predictor boltz --sequence-designer solublempnn \
  --template-yaml my_target.yaml --run-name my_campaign \
  --num-runs 20 --num-opt-cycles 5 \
  --model v2-flash \
  --random-binder --binder-min-len 60 --binder-max-len 120 \
  --post-predictor intellifold --post-mode iptm --post-iptm-threshold 0.7 \
  --target-msa-mode auto --target-msa-generator auto --require-target-msa \
  --max-parallel auto --throughput-profile auto --resume
```

Flags worth knowing:

| Flag | Why |
|---|---|
| `--require-target-msa` | an unreachable MSA server otherwise degrades the run to single-sequence silently |
| `--throughput-profile auto` | uses a measured per-machine schedule, and *rejects* one from a different Mac |
| `--resume` | idempotent; reuses completed cycles after an interruption |
| `--design-scheduler cycle-wave` | native batching — where AlphaFold 3 and IntelliFold win most |
| `--model v2-flash` | choose `v2-flash` or the larger full `v2` IntelliFold model |

Leave `--intellifold-buckets` and `--alphafold3-buckets` alone. Their `auto`
default resolves to the exact campaign token count, which is the single largest
measured speed-up available; setting them explicitly undoes it.

To target specific atoms of a small molecule, get the names Boltz will use —
**they change when the affinity head is on**, because it standardises the SMILES
first:

```bash
"$ROOT/venvs/NanoHunter_boltz/bin/python" "$ROOT/rfd3_scripts/boltz_ligand_atoms.py" \
  'O=C(NCCO)c1ccc…' 1        # 1 = affinity head on
```

then write them into the template as a `pocket` constraint and run with
`--boltz-use-potentials` — without potentials a forced constraint barely steers.

---

## RFdiffusion3

```bash
cd "$ROOT/rfd3"

# Understand the ligand first: chemistry checks, which shapes it adopts,
# how the design budget should be split
"$ROOT/venvs/NanoHunter_boltz/bin/python" "$ROOT/rfd3_scripts/ligand_intelligence.py" request.json

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
  msa_cache/                 shared alignments, indexed by sequence
  scaffold_msa_cache/        bundled deep MSAs for all seven nanobody scaffolds
  projects/<slug>/           campaign and prediction outputs
```
